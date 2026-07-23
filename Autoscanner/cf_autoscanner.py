"""
Cloudflare IP scan engine - multi-Zone / multi-Record version
This file lives inside the Autoscanner folder; settings and history are also read/written from this same folder.
"""
import os
import json
import socket
import ssl
import time
import random
import ipaddress
import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict, Set

from . import autoscanner_settings as settings

logger = logging.getLogger(__name__)

# ==================================================
# Config (technical constants, no need for admin to change these)
# ==================================================
TEST_SNI = "speed.cloudflare.com"
TEST_TIMEOUT = 2.0
TEST_RETRIES = 3
MAX_NEW_IPS = 50
UPDATE_THRESHOLD = 20.0

UPLOAD_TEST_PATH = "/__up"
UPLOAD_TEST_SIZE = 256 * 1024
UPLOAD_TEST_TIMEOUT = 5.0
UPLOAD_CANDIDATES_PER_ROUND = 5
MAX_SCAN_ROUNDS = int(os.getenv("MAX_SCAN_ROUNDS", "10"))

# check-host.net (IR nodes) pre-check
CHECKHOST_BASE = "https://check-host.net"
CHECKHOST_IR_NODES = [
    "ir2.node.check-host.net",  # Isfahan
    "ir3.node.check-host.net",  # Shiraz
    "ir4.node.check-host.net",  # Shiraz
    "ir5.node.check-host.net",  # Tehran
    "ir6.node.check-host.net",  # Qom
    "ir7.node.check-host.net",  # Tehran
    "ir8.node.check-host.net",  # Tehran
    "ir9.node.check-host.net",  # Khonj
]
CHECKHOST_IR_NODE_LABELS = {
    "ir2.node.check-host.net": "Isfahan",
    "ir3.node.check-host.net": "Shiraz 1",
    "ir4.node.check-host.net": "Shiraz 2",
    "ir5.node.check-host.net": "Tehran 1",
    "ir6.node.check-host.net": "Qom",
    "ir7.node.check-host.net": "Tehran 2",
    "ir8.node.check-host.net": "Tehran 3",
    "ir9.node.check-host.net": "Khonj",
}
CHECKHOST_MAX_LOSS_PERCENT = float(os.getenv("CHECKHOST_MAX_LOSS_PERCENT", "25"))
CHECKHOST_MIN_OK_NODES = int(os.getenv("CHECKHOST_MIN_OK_NODES", "4"))
CHECKHOST_POLL_INTERVAL = 1.5
CHECKHOST_MAX_WAIT = 15.0
CHECKHOST_POST_UPDATE_DELAY = float(os.getenv("CHECKHOST_POST_UPDATE_DELAY", "3"))


# Since this file is inside the Autoscanner folder, the history is also stored right next to it
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "autoscanner_history.json")


# ==================================================
# History
# ==================================================
def _load_history() -> List[str]:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load history: {e}")
    return []


def _save_history(ips: List[str]):
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(ips[:10], f)
    except Exception as e:
        logger.error(f"Failed to save history: {e}")


# ==================================================
# Network & TLS Testing
# ==================================================
def _measure_tls_latency(ip: str, sni: str, port: int, timeout: float) -> Optional[float]:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    start_time = time.perf_counter()
    try:
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=sni):
                return (time.perf_counter() - start_time) * 1000
    except (socket.timeout, ConnectionRefusedError, ssl.SSLError, OSError):
        return None


def _evaluate_ip(ip: str, port: int) -> Optional[Dict]:
    latencies = []
    for _ in range(TEST_RETRIES):
        lat = _measure_tls_latency(ip, TEST_SNI, port, TEST_TIMEOUT)
        if lat is not None:
            latencies.append(lat)
        time.sleep(0.1)

    success_count = len(latencies)
    if success_count == 0:
        return None

    packet_loss = 1.0 - (success_count / TEST_RETRIES)
    avg_lat = sum(latencies) / success_count
    jitter = max(latencies) - min(latencies) if success_count > 1 else 0
    score = avg_lat + (jitter * 0.5) + (packet_loss * 2000)

    return {"ip": ip, "port": port, "avg": avg_lat, "jitter": jitter,
            "loss": packet_loss * 100, "score": score}


def _measure_upload_speed(ip: str, sni: str, port: int, timeout: float,
                           payload_size: int = UPLOAD_TEST_SIZE) -> Optional[float]:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    data = os.urandom(payload_size)
    request = (
        f"POST {UPLOAD_TEST_PATH} HTTP/1.1\r\n"
        f"Host: {sni}\r\n"
        f"Content-Length: {len(data)}\r\n"
        f"Content-Type: application/octet-stream\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode() + data

    try:
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=sni) as ssock:
                ssock.settimeout(timeout)
                start = time.perf_counter()
                ssock.sendall(request)

                response = b""
                while b"\r\n\r\n" not in response and len(response) < 65536:
                    chunk = ssock.recv(4096)
                    if not chunk:
                        break
                    response += chunk

                elapsed = time.perf_counter() - start
                if not response:
                    return None

                status_line = response.split(b"\r\n", 1)[0].decode(errors="ignore")
                if " 200" not in status_line and " 204" not in status_line:
                    return None
                if elapsed <= 0:
                    return None

                return (payload_size * 8) / (elapsed * 1_000_000)
    except (socket.timeout, ConnectionRefusedError, ssl.SSLError, OSError):
        return None


def _verify_ip_with_upload(ip: str, port: int) -> Optional[Dict]:
    speed = _measure_upload_speed(ip, TEST_SNI, port, UPLOAD_TEST_TIMEOUT)
    if speed is None:
        return None
    return {"ip": ip, "port": port, "upload_mbps": speed}


def _check_ping_ir(host: str) -> Optional[Dict]:
    """
    Runs a ping check against `host` (a raw IP or a domain name) from check-host.net's
    Iranian nodes. Works for both:
      - a candidate Cloudflare IP (before it's assigned to the domain)
      - the domain itself (after the DNS record has been updated)

    Returns None if the request couldn't be submitted or too few nodes answered in time.
    Otherwise returns:
        {
            "loss_percent": float,        # overall ping loss across all reporting nodes
            "avg_ms": float | None,
            "nodes_total": int,           # IR nodes asked
            "nodes_reported": int,        # nodes that answered at all before the deadline
            "nodes_unresolved": int,      # nodes that couldn't resolve the host at all ("Unknown host")
            "nodes_fully_blocked": int,   # nodes that resolved it but got 0/N replies (shown as
                                           # "Traceroute" in the check-host.net web UI)
        }
    """
    try:
        # multiple node=... params are needed, so the query string is built manually
        node_qs = "&".join(f"node={n}" for n in CHECKHOST_IR_NODES)
        resp = requests.get(
            f"{CHECKHOST_BASE}/check-ping?host={host}&{node_qs}",
            headers={"Accept": "application/json"},
            timeout=10,
        )
        data = resp.json()
        if not data.get("ok"):
            return None
        request_id = data["request_id"]
        expected_nodes = set(data.get("nodes", {}).keys()) or set(CHECKHOST_IR_NODES)
    except Exception as e:
        logger.warning(f"check-host.net request failed for {host}: {e}")
        return None

    deadline = time.time() + CHECKHOST_MAX_WAIT
    results = {}
    while time.time() < deadline:
        try:
            r = requests.get(
                f"{CHECKHOST_BASE}/check-result/{request_id}",
                headers={"Accept": "application/json"},
                timeout=10,
            )
            results = r.json() or {}
        except Exception as e:
            logger.warning(f"check-host.net poll failed for {host}: {e}")
            break

        # keep polling until every node has answered (or we run out of time)
        if all(results.get(n) is not None for n in expected_nodes):
            break
        time.sleep(CHECKHOST_POLL_INTERVAL)

    total_pings = 0
    ok_pings = 0
    ok_latencies = []
    nodes_reported = 0
    nodes_unresolved = 0
    nodes_fully_blocked = 0
    node_details = []  # one entry per IR node, in the order defined by CHECKHOST_IR_NODES

    for node in CHECKHOST_IR_NODES:
        if node not in expected_nodes:
            continue
        city = CHECKHOST_IR_NODE_LABELS.get(node, node)
        node_result = results.get(node)

        if not node_result or not node_result[0]:
            node_details.append({"city": city, "status": "timeout", "loss_percent": None, "avg_ms": None})
            continue  # node never answered before the deadline

        pings = node_result[0]
        nodes_reported += 1

        if pings == [None]:
            # check-host.net's way of saying it couldn't resolve the host at all
            nodes_unresolved += 1
            node_details.append({"city": city, "status": "unresolved", "loss_percent": None, "avg_ms": None})
            continue

        node_ok = 0
        node_total = 0
        node_latencies = []
        for ping in pings:
            node_total += 1
            total_pings += 1
            if ping and ping[0] == "OK":
                node_ok += 1
                ok_pings += 1
                node_latencies.append(ping[1] * 1000)
                ok_latencies.append(ping[1] * 1000)

        node_loss = (1 - node_ok / node_total) * 100 if node_total else 100.0
        node_avg = sum(node_latencies) / len(node_latencies) if node_latencies else None

        if node_ok == 0:
            # resolved fine, but zero replies out of N pings -> fully blocked/filtered from that node
            nodes_fully_blocked += 1
            node_details.append({"city": city, "status": "blocked", "loss_percent": node_loss, "avg_ms": None,
                                  "ok_count": node_ok, "total_count": node_total})
        else:
            node_details.append({"city": city, "status": "ok", "loss_percent": node_loss, "avg_ms": node_avg,
                                  "ok_count": node_ok, "total_count": node_total})

    if nodes_reported < CHECKHOST_MIN_OK_NODES:
        return None

    # Loss is averaged per-datacenter (each Iranian node weighted equally), not per-ping.
    # A node that couldn't resolve the host at all ("unresolved") or that resolved it but
    # got zero replies ("blocked") counts as 100% loss for that datacenter. Previously,
    # unresolved nodes were skipped entirely from this calculation, which could report a
    # misleadingly low (even 0%) overall loss while several datacenters couldn't reach the
    # host at all - masking real DNS/blocking problems.
    node_loss_values = [
        100.0 if nd["status"] in ("unresolved", "blocked") else nd["loss_percent"]
        for nd in node_details
        if nd["status"] != "timeout"
    ]
    loss_percent = sum(node_loss_values) / len(node_loss_values) if node_loss_values else 100.0
    avg_ms = sum(ok_latencies) / len(ok_latencies) if ok_latencies else None

    return {
        "loss_percent": loss_percent,
        "avg_ms": avg_ms,
        "nodes_total": len(expected_nodes),
        "nodes_reported": nodes_reported,
        "nodes_unresolved": nodes_unresolved,
        "nodes_fully_blocked": nodes_fully_blocked,
        "node_details": node_details,
    }


def _check_iran_packet_loss(ip: str) -> Optional[Dict]:
    """Thin wrapper used while scanning candidate IPs (see _find_verified_best_ip)."""
    return _check_ping_ir(ip)


def _check_domain_health(domain: str) -> Dict:
    """
    Re-tests the domain itself (after its DNS record has just been updated) from the
    same Iranian check-host.net nodes, and reports whether it needs attention:
      - some nodes can't resolve it at all (DNS/propagation problem), or
      - some nodes resolve it but get no ping replies at all (network-level blocking;
        this is the case that shows up as "Traceroute" in the check-host.net UI).

    Always returns a dict (never None) so callers can report on it unconditionally:
        {"checked": bool, "needs_attention": bool, "message": str, ...}
    """
    stat = _check_ping_ir(domain)
    if stat is None:
        return {
            "checked": False,
            "needs_attention": False,
            "message": "Not enough reports were received from Iranian datacenters for the domain.",
        }

    problems = []
    if stat["nodes_unresolved"] > 0:
        problems.append(f"{stat['nodes_unresolved']} datacenter(s) failed to resolve the domain (Unknown host)")
    if stat["nodes_fully_blocked"] > 0:
        problems.append(f"{stat['nodes_fully_blocked']} datacenter(s) got no reply at all (Traceroute)")

    needs_attention = stat["nodes_unresolved"] > 0 or stat["nodes_fully_blocked"] > 0

    if needs_attention:
        message = "🚨Your domain needs attention!!!"
    else:
        message = (f"✅ Domain is healthy from {stat['nodes_reported']}/{stat['nodes_total']} Iran datacenters "
                    f"(loss={stat['loss_percent']:.0f}%)")

    return {
        "checked": True,
        "needs_attention": needs_attention,
        "message": message,
        "loss_percent": stat["loss_percent"],
        "nodes_unresolved": stat["nodes_unresolved"],
        "nodes_fully_blocked": stat["nodes_fully_blocked"],
        "node_details": stat["node_details"],
    }


# ==================================================
# IP Gathering & Scanning
# ==================================================
def _get_random_ip(cidr: str) -> Optional[str]:
    try:
        network = ipaddress.ip_network(cidr, strict=False)
        min_host = int(network.network_address) + 1
        max_host = int(network.broadcast_address) - 1
        if min_host <= max_host:
            return str(ipaddress.IPv4Address(random.randint(min_host, max_host)))
        return None
    except ValueError:
        return None


def _fetch_cf_ranges(session: requests.Session) -> List[str]:
    url = "https://raw.githubusercontent.com/ircfspace/cf-ip-ranges/main/export.ipv4"
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        return [line.strip() for line in response.text.splitlines() if line.strip()]
    except Exception as e:
        logger.error(f"Failed to fetch Cloudflare IP ranges: {e}")
        return []


def _gather_candidate_ips(ranges: List[str], exclude: Set[str], count: int) -> List[str]:
    candidates = []
    shuffled = ranges[:]
    random.shuffle(shuffled)
    for cidr in shuffled:
        if len(candidates) >= count:
            break
        ip = _get_random_ip(cidr) if "/" in cidr else cidr
        if ip and ip not in exclude:
            candidates.append(ip)
            exclude.add(ip)
    return candidates


def _scan_latency(ips: List[str], port: int) -> List[Dict]:
    results = []
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(_evaluate_ip, ip, port) for ip in ips]
        for future in as_completed(futures):
            res = future.result()
            if res:
                results.append(res)
    results.sort(key=lambda x: x["score"])
    return results


def _find_verified_best_ip(ranges: List[str], port: int, exclude_ips: Set[str],
                            round_callback=None, notify=None) -> Optional[Dict]:
    round_num = 0
    while round_num < MAX_SCAN_ROUNDS:
        round_num += 1
        candidates = _gather_candidate_ips(ranges, exclude_ips, MAX_NEW_IPS)
        if not candidates:
            logger.warning(f"[port {port}] No more fresh IPs left to try.")
            if round_callback:
                round_callback(round_num, MAX_SCAN_ROUNDS, "no_fresh_ips")
            break

        logger.info(f"[port {port}] Round {round_num}/{MAX_SCAN_ROUNDS}: scanning {len(candidates)} IPs...")
        if round_callback:
            round_callback(round_num, MAX_SCAN_ROUNDS, "scanning")

        latency_results = _scan_latency(candidates, port)
        if not latency_results:
            continue

        top_n = latency_results[:UPLOAD_CANDIDATES_PER_ROUND]
        for stat in top_n:
            upload_result = _verify_ip_with_upload(stat["ip"], port)
            if upload_result is None:
                continue
            stat["upload_mbps"] = upload_result["upload_mbps"]

            ir_check = _check_iran_packet_loss(stat["ip"])
            if ir_check is None:
                logger.info(f"[port {port}] {stat['ip']}: no check-host.net result, skipping.")
                continue

            passed = ir_check["loss_percent"] <= CHECKHOST_MAX_LOSS_PERCENT
            if notify:
                notify({
                    "type": "checkhost_result",
                    "phase": "candidate",
                    "port": port,
                    "ip": stat["ip"],
                    "passed": passed,
                    "loss_percent": ir_check["loss_percent"],
                    "node_details": ir_check["node_details"],
                })
            if not passed:
                logger.info(f"[port {port}] {stat['ip']}: rejected, IR loss "
                            f"{ir_check['loss_percent']:.0f}% > {CHECKHOST_MAX_LOSS_PERCENT:.0f}%")
                continue

            stat["ir_loss_percent"] = ir_check["loss_percent"]
            stat["ir_avg_ms"] = ir_check["avg_ms"]

            logger.info(f"[port {port}] Verified IP: {stat['ip']} (score={stat['score']:.0f}, "
                        f"upload={stat['upload_mbps']:.2f} Mbps, "
                        f"IR loss={ir_check['loss_percent']:.0f}%)")
            if round_callback:
                round_callback(round_num, MAX_SCAN_ROUNDS, "found")
            return stat

    logger.error(f"[port {port}] No verified IP found after {round_num} round(s).")
    return None


# ==================================================
# Cloudflare DNS Update (parameterized - multi Zone)
# ==================================================
def _update_dns_record(session: requests.Session, cf_api_token: str, zone_id: str,
                        record_name: str, best_ip_stat: Dict, force: bool = False) -> Dict:
    """Updates a specific A Record in a specific Zone. The output is a dict summarizing the result.

    force=True skips the "insufficient improvement" quality-comparison guard and always
    applies the new IP (used when the current IP has been shown to fail from Iran at the
    domain level, so keeping it - even if its raw latency score looks fine - is not an
    option)."""
    new_ip = best_ip_stat["ip"]
    new_score = best_ip_stat["score"]
    port = best_ip_stat["port"]

    headers = {"Authorization": f"Bearer {cf_api_token}", "Content-Type": "application/json"}
    base_url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"

    result = {"record": record_name, "port": port, "new_ip": new_ip, "updated": False, "message": ""}

    try:
        resp = session.get(f"{base_url}?name={record_name}&type=A", headers=headers, timeout=10)
        data = resp.json()

        if not data.get("success"):
            result["message"] = f"Cloudflare API error: {data.get('errors')}"
            return result

        records = data.get("result", [])

        # If an A record with this name doesn't exist yet, create it ourselves
        if not records:
            create_payload = {
                "type": "A", "name": record_name, "content": new_ip,
                "ttl": 60, "proxied": False,
            }
            create_resp = session.post(base_url, headers=headers, json=create_payload, timeout=10)
            create_data = create_resp.json()

            if create_data.get("success"):
                result["updated"] = True
                result["message"] = f"New record created ➡️ `{new_ip}`"
            else:
                result["message"] = f"Error creating new record: {create_data.get('errors')}"

            return result

        record = records[0]
        current_ip = record["content"]

        if current_ip == new_ip:
            result["message"] = "Already the current IP; no update needed."
            result["updated"] = False
            return result

        if not force:
            current_ip_stat = _evaluate_ip(current_ip, port)
            if current_ip_stat:
                improvement = current_ip_stat["score"] - new_score
                if improvement < UPDATE_THRESHOLD:
                    result["message"] = f"Current IP quality is still good (insufficient improvement: {improvement:.0f})."
                    return result

        payload = {"type": "A", "name": record_name, "content": new_ip, "ttl": 60, "proxied": False}
        update_resp = session.put(f"{base_url}/{record['id']}", headers=headers, json=payload, timeout=10)
        update_data = update_resp.json()

        if update_data.get("success"):
            result["updated"] = True
            result["message"] = f"`{current_ip}` ➡️ `{new_ip}`"
        else:
            result["message"] = f"Update error: {update_data.get('errors')}"

        return result
    except Exception as e:
        result["message"] = f"Internal error: {e}"
        return result


# ==================================================
# Main entry point: one full scan cycle for all configured records
# ==================================================
def run_scan_cycle(progress_callback=None, records: Optional[List[Dict]] = None) -> Dict:
    """
    Runs one full scan cycle:
    - Based on the given records (or, if empty, all records registered by the admin),
      extracts the unique ports
    - Finds a verified IP (latency + real upload) for each port
    - As soon as an IP is found for a port, the DNS records for that port are updated immediately
      (it does not wait for the scanning of other ports to finish)

    records (optional): a subset of records to run the scan on only those
    (e.g. when the admin has selected specific records from the immediate-run menu).
    If None, all records registered in settings are used.

    progress_callback (optional): a function called with a dict shaped as below to report
    scan progress. This function may be called from a separate thread:
        {"type": "round", "port": ..., "round": ..., "max_rounds": ..., "status": ...,
         "port_index": ..., "total_ports": ...}
        {"type": "port_done", "port": ..., "found": bool, "ip": ..., "port_index": ..., "total_ports": ...}
        {"type": "record_updated", "name": ..., "port": ..., "updated": bool, "message": ..., "new_ip": ...}

    Output: a summary dict containing the status of each record + any top-level errors
    """
    summary = {"ok": True, "error": None, "ports_scanned": [], "records": []}

    def _notify(event: dict):
        if progress_callback:
            try:
                progress_callback(event)
            except Exception as e:
                logger.error(f"progress_callback error: {e}")

    cf_api_token = settings.get_cf_api_token()
    if records is None:
        records = settings.get_records()

    if not cf_api_token:
        summary["ok"] = False
        summary["error"] = "Cloudflare token is not set."
        return summary

    if not records:
        summary["ok"] = False
        summary["error"] = "No records registered."
        return summary

    with requests.Session() as session:
        ranges = _fetch_cf_ranges(session)
        if not ranges:
            summary["ok"] = False
            summary["error"] = "Failed to fetch Cloudflare IP ranges."
            return summary

        exclude_ips: Set[str] = set(_load_history())

        # Extract unique ports so each port is only scanned once
        unique_ports = sorted({r["port"] for r in records})
        total_ports = len(unique_ports)
        found_ips: List[str] = []

        # Instead of re-testing the domain itself for every single record (slow, and
        # redundant), we only test ONE domain at the very end: whichever record's IP was
        # verified with the lowest (ideally zero) packet loss at the IP level. That IP is
        # the "champion" - if the domain still shows loss when tested by name using that
        # champion IP, the problem is with the domain/SNI itself, not the IP.
        champion = None  # {"rec_result": <dict in summary["records"]>, "name": ..., "loss": ..., "just_updated": bool, "port_index": ...}

        for port_index, port in enumerate(unique_ports):

            def _round_cb(round_num, max_rounds, status, _port=port, _idx=port_index):
                _notify({
                    "type": "round",
                    "port": _port,
                    "round": round_num,
                    "max_rounds": max_rounds,
                    "status": status,
                    "port_index": _idx,
                    "total_ports": total_ports,
                })

            def _checkhost_notify(event, _idx=port_index):
                _notify({**event, "port_index": _idx, "total_ports": total_ports})

            best_stat = _find_verified_best_ip(ranges, port, exclude_ips,
                                                round_callback=_round_cb, notify=_checkhost_notify)

            summary["ports_scanned"].append({
                "port": port,
                "found": best_stat is not None,
                "ip": best_stat["ip"] if best_stat else None,
            })
            if best_stat:
                found_ips.append(best_stat["ip"])

            _notify({
                "type": "port_done",
                "port": port,
                "found": best_stat is not None,
                "ip": best_stat["ip"] if best_stat else None,
                "port_index": port_index,
                "total_ports": total_ports,
            })

            # As soon as this port's IP is found (or not found), immediately update this port's records
            # (we don't wait for the scanning of subsequent ports to finish)
            port_records = [r for r in records if r["port"] == port]
            for rec in port_records:
                zone = settings.get_zone(rec["zone_id"])
                if not zone:
                    rec_result = {
                        "name": rec["name"], "port": rec["port"],
                        "updated": False, "message": "The associated Zone no longer exists.",
                        "new_ip": None,
                        "domain_needs_attention": False, "domain_message": None,
                    }
                elif not best_stat:
                    rec_result = {
                        "name": rec["name"], "port": rec["port"],
                        "updated": False, "message": "No verified IP was found for this port.",
                        "new_ip": None,
                        "domain_needs_attention": False, "domain_message": None,
                    }
                else:
                    result = _update_dns_record(session, cf_api_token, zone["id"], rec["name"], best_stat)

                    rec_result = {
                        "name": rec["name"], "port": rec["port"],
                        "updated": result["updated"], "message": result["message"],
                        "new_ip": result.get("new_ip"),
                        "domain_needs_attention": False,
                        "domain_message": None,
                    }

                    # Track this record as the champion if its IP had lower (verified)
                    # packet loss than whichever record is champion so far. best_stat's
                    # ir_loss_percent was already measured directly against the IP itself.
                    ip_loss = best_stat.get("ir_loss_percent")
                    if ip_loss is not None and (champion is None or ip_loss < champion["loss"]):
                        champion = {
                            "rec_result": rec_result,
                            "name": rec["name"],
                            "loss": ip_loss,
                            "just_updated": result["updated"],
                            "port_index": port_index,
                            "zone_id": rec["zone_id"],
                            "ip": best_stat["ip"],
                        }

                summary["records"].append(rec_result)
                _notify({"type": "record_updated", **rec_result})

            # Keep the history up to date too, so that if the scan is interrupted partway through,
            # the IPs found up to this point are already saved
            if found_ips:
                _save_history(found_ips)

        # Now that every port has been scanned and all records updated, test the domain
        # for just the single champion record - the one whose IP had the lowest (ideally
        # zero) packet loss at the IP level. If the domain still shows loss by name using
        # that already-verified-clean IP, the issue is with the domain/SNI itself.
        if champion is not None:
            if champion["just_updated"]:
                # give resolvers a moment before re-testing the domain itself
                time.sleep(CHECKHOST_POST_UPDATE_DELAY)

            domain_health = _check_domain_health(champion["name"])
            if domain_health["checked"]:
                champion["rec_result"]["domain_needs_attention"] = domain_health["needs_attention"]
                champion["rec_result"]["domain_message"] = domain_health["message"]
                # Full per-datacenter grid + pass/fail + loss, so the UI can render the
                # domain-level check the same way it renders the candidate-IP check,
                # instead of collapsing it into a single summary line.
                champion["rec_result"]["domain_passed"] = not domain_health["needs_attention"]
                champion["rec_result"]["domain_loss_percent"] = domain_health["loss_percent"]
                champion["rec_result"]["domain_node_details"] = domain_health["node_details"]
                _notify({
                    "type": "checkhost_result",
                    "phase": "domain",
                    "name": champion["name"],
                    "port": champion["rec_result"]["port"],
                    "passed": not domain_health["needs_attention"],
                    "loss_percent": domain_health["loss_percent"],
                    "node_details": domain_health["node_details"],
                    "message": domain_health["message"],
                    "port_index": champion["port_index"],
                    "total_ports": total_ports,
                })

                # The domain itself fails to resolve/respond from some Iranian datacenters
                # even though its current IP passed the (looser) candidate-level check.
                # Leaving it as-is just because the latency score "looked good enough" is
                # not acceptable here, so force a fresh IP onto this record.
                if domain_health["needs_attention"]:
                    zone = settings.get_zone(champion["zone_id"])
                    if zone:
                        exclude_ips.add(champion["ip"])
                        fix_stat = _find_verified_best_ip(ranges, champion["rec_result"]["port"], exclude_ips)
                        if fix_stat:
                            fix_result = _update_dns_record(
                                session, cf_api_token, zone["id"], champion["name"], fix_stat, force=True
                            )
                            if fix_result["updated"]:
                                champion["rec_result"]["updated"] = True
                                champion["rec_result"]["new_ip"] = fix_result.get("new_ip")
                                champion["rec_result"]["domain_fix_message"] = (
                                    f"Switched to a fresh IP → `{fix_result.get('new_ip')}`."
                                )
                                found_ips.append(fix_stat["ip"])
                                _save_history(found_ips)
                            else:
                                champion["rec_result"]["domain_fix_message"] = (
                                    f"Applying a fresh IP also failed: {fix_result['message']}"
                                )
                        else:
                            champion["rec_result"]["domain_fix_message"] = (
                                "No alternate verified IP could be found to replace it."
                            )
                    else:
                        champion["rec_result"]["domain_fix_message"] = (
                            "Its Zone no longer exists, so no fix could be applied."
                        )

                _notify({"type": "record_updated", **champion["rec_result"]})

    return summary
