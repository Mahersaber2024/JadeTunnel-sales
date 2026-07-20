<?php
// ============================================================
// Subscription Proxy - Iran Host
// ============================================================

const API_BASE = '';
const API_KEY  = '';

const SPONSOR_HTML = '
<div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 0.9rem;">
    🌟 Sponsored by <a href="https://t.me/HeySoloATM" target="_blank" style="color:#1a73e8; text-decoration:none; font-weight:bold;">@HeySoloATM</a> – Subscription link costs covered.
</div>';

function fetch_api(string $path) {
    $url = API_BASE . $path;
    $ch = curl_init();
    $headers = ['Accept: application/json'];
    if (API_KEY !== '') {
        $headers[] = 'X-API-Key: ' . API_KEY;
    }
    curl_setopt($ch, CURLOPT_URL, $url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
    curl_setopt($ch, CURLOPT_TIMEOUT, 20);
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
    curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, false);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);

    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $err = curl_error($ch);
    curl_close($ch);

    return [$httpCode, $response, $err];
}

function is_real_browser(string $userAgent, string $acceptHeader): bool {
    $looksLikeBrowserUA = (bool) preg_match(
        '/(Chrome|Firefox|Safari|Opera|OPR|Edge|Edg|MSIE|Trident)/i',
        $userAgent
    );
    $acceptsHtml = stripos($acceptHeader, 'text/html') !== false;
    return $looksLikeBrowserUA && $acceptsHtml;
}

// ---- تابع مشترک برای رندر صفحه‌ی HTML (هم برای ترکیبی، هم برای تک‌اشتراکی) ----
function render_html_page(string $userId, array $subs) {
    header('Content-Type: text/html; charset=utf-8');

    echo '<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>🔑 Your Subscriptions | Jade Tunnel</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body {
                font-family: system-ui, -apple-system, "Segoe UI", Roboto, Tahoma, sans-serif;
                background: linear-gradient(135deg, #0b0e1a 0%, #1a1f35 100%);
                min-height: 100vh;
                padding: 20px;
                color: #e0e4f0;
            }
            .container {
                max-width: 900px;
                margin: 0 auto;
                background: rgba(255,255,255,0.05);
                backdrop-filter: blur(12px);
                border-radius: 24px;
                padding: 30px;
                border: 1px solid rgba(255,255,255,0.08);
                box-shadow: 0 25px 50px rgba(0,0,0,0.5);
            }
            .header {
                text-align: center;
                padding-bottom: 24px;
                border-bottom: 1px solid rgba(255,255,255,0.08);
                margin-bottom: 24px;
            }
            .header h2 {
                font-size: 1.8rem;
                background: linear-gradient(90deg, #6dd5fa, #a78bfa);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            .header p {
                color: #94a3b8;
                margin-top: 6px;
                font-size: 0.9rem;
            }
            .header code {
                background: rgba(255,255,255,0.08);
                padding: 2px 10px;
                border-radius: 6px;
                font-size: 0.85rem;
                color: #e2e8f0;
            }
            .sub-item {
                background: rgba(255,255,255,0.04);
                border-radius: 16px;
                padding: 20px 24px;
                margin-bottom: 18px;
                border: 1px solid rgba(255,255,255,0.06);
                transition: all 0.2s;
            }
            .sub-item:hover {
                background: rgba(255,255,255,0.08);
                border-color: rgba(255,255,255,0.12);
            }
            .sub-title {
                font-size: 1.15rem;
                font-weight: 600;
                color: #f0f4ff;
                margin-bottom: 6px;
            }
            .sub-meta {
                display: flex;
                flex-wrap: wrap;
                gap: 14px;
                font-size: 0.85rem;
                color: #94a3b8;
                margin-bottom: 10px;
            }
            .sub-meta span {
                background: rgba(255,255,255,0.05);
                padding: 2px 12px;
                border-radius: 20px;
            }
            .sub-email {
                font-size: 0.85rem;
                color: #94a3b8;
                margin-bottom: 10px;
            }
            .sub-email code {
                background: rgba(255,255,255,0.06);
                padding: 1px 8px;
                border-radius: 4px;
                font-size: 0.8rem;
            }
            .sub-links { margin-top: 12px; }
            .link-item {
                display: flex;
                align-items: center;
                gap: 10px;
                background: rgba(0,0,0,0.25);
                padding: 8px 12px;
                border-radius: 10px;
                margin-bottom: 6px;
                flex-wrap: wrap;
            }
            .link-item .link-num {
                color: #6dd5fa;
                font-weight: 500;
                font-size: 0.8rem;
                min-width: 24px;
            }
            .link-item .link-code {
                flex: 1;
                font-size: 0.75rem;
                color: #cbd5e1;
                word-break: break-all;
                background: rgba(255,255,255,0.03);
                padding: 4px 8px;
                border-radius: 6px;
                min-width: 150px;
                cursor: pointer;
            }
            .copy-btn {
                background: rgba(109, 213, 250, 0.12);
                border: 1px solid rgba(109, 213, 250, 0.2);
                color: #6dd5fa;
                padding: 4px 14px;
                border-radius: 8px;
                cursor: pointer;
                font-size: 0.75rem;
                transition: all 0.2s;
            }
            .copy-btn:hover {
                background: rgba(109, 213, 250, 0.2);
                border-color: #6dd5fa;
            }
            .no-links {
                color: #f59e0b;
                font-size: 0.85rem;
                padding: 6px 0;
            }
            .empty {
                text-align: center;
                padding: 40px 20px;
                color: #94a3b8;
            }
            .footer {
                text-align: center;
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid rgba(255,255,255,0.06);
                font-size: 0.85rem;
                color: #64748b;
            }
            .sponsor-badge {
                display: inline-block;
                background: rgba(167, 139, 250, 0.12);
                padding: 6px 18px;
                border-radius: 30px;
                font-size: 0.8rem;
                border: 1px solid rgba(167, 139, 250, 0.15);
            }
            .sponsor-badge a { color: #a78bfa; text-decoration: none; }
            .toast {
                position: fixed;
                bottom: 30px;
                left: 50%;
                transform: translateX(-50%);
                background: rgba(0,0,0,0.85);
                color: #e2e8f0;
                padding: 12px 28px;
                border-radius: 14px;
                font-size: 0.9rem;
                backdrop-filter: blur(8px);
                border: 1px solid rgba(255,255,255,0.08);
                opacity: 0;
                transition: opacity 0.3s;
                pointer-events: none;
                z-index: 999;
            }
            .toast.show { opacity: 1; }
            @media (max-width: 640px) {
                .container { padding: 16px; }
                .sub-item { padding: 14px 16px; }
                .link-item { flex-wrap: wrap; }
                .link-item .link-code { min-width: 100%; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>🔗 Your Subscription Links</h2>
                <p>User ID: <code>' . htmlspecialchars($userId) . '</code></p>
            </div>';

    if (empty($subs)) {
        echo '<div class="empty">⚠️ No active subscriptions found.</div>';
    } else {
        foreach ($subs as $sub) {
            $planName  = htmlspecialchars($sub['plan_name'] ?? 'Plan', ENT_QUOTES, 'UTF-8');
            $panelName = htmlspecialchars($sub['panel_name'] ?? 'Panel', ENT_QUOTES, 'UTF-8');
            $endDate   = htmlspecialchars($sub['end_date'] ?? '-', ENT_QUOTES, 'UTF-8');
            $startDate = htmlspecialchars($sub['start_date'] ?? '-', ENT_QUOTES, 'UTF-8');
            $volume    = $sub['remaining_volume'] ?? null;
            $email     = htmlspecialchars($sub['email'] ?? '', ENT_QUOTES, 'UTF-8');

            echo '<div class="sub-item">';
            echo '<div class="sub-title">📦 ' . $planName . '</div>';
            echo '<div class="sub-meta">';
            echo '<span>🖥 ' . $panelName . '</span>';
            if ($volume !== null) {
                echo '<span>📊 ' . (int)$volume . ' GB</span>';
            }
            echo '<span>📅 Start: ' . $startDate . '</span>';
            echo '<span>📅 Expiry: ' . $endDate . '</span>';
            echo '</div>';

            if (!empty($email)) {
                echo '<div class="sub-email">📧 <code>' . $email . '</code></div>';
            }

            $links = $sub['links'] ?? [];
            if (!empty($links)) {
                echo '<div class="sub-links">';
                foreach ($links as $i => $link) {
                    $safeLink = htmlspecialchars($link, ENT_QUOTES, 'UTF-8');
                    $idAttr = 'cfg_' . uniqid();
                    echo '<div class="link-item">';
                    echo '<span class="link-num">' . ($i + 1) . '.</span>';
                    echo '<span class="link-code" id="' . $idAttr . '">' . $safeLink . '</span>';
                    echo '<button class="copy-btn" onclick="copyText(\'' . $idAttr . '\', this)">📋 Copy</button>';
                    echo '</div>';
                }
                echo '</div>';
            } else {
                echo '<div class="no-links">⚠️ No links found for this subscription</div>';
            }

            echo '</div>';
        }
    }

    echo '
            <div class="footer">
                <div class="sponsor-badge">' . SPONSOR_HTML . '</div>
            </div>
        </div>

        <div id="toast" class="toast">✅ Copied!</div>

        <script>
            function copyText(id, btn) {
                var text = document.getElementById(id).innerText;
                navigator.clipboard.writeText(text).then(function() {
                    showCopied(btn);
                }).catch(function() {
                    var textarea = document.createElement("textarea");
                    textarea.value = text;
                    document.body.appendChild(textarea);
                    textarea.select();
                    document.execCommand("copy");
                    document.body.removeChild(textarea);
                    showCopied(btn);
                });
            }
            function showCopied(btn) {
                var old = btn.innerText;
                btn.innerText = "✅ Copied";
                var toast = document.getElementById("toast");
                toast.classList.add("show");
                setTimeout(function() {
                    toast.classList.remove("show");
                    btn.innerText = old;
                }, 2000);
            }
            document.querySelectorAll(".link-code").forEach(function(el) {
                el.addEventListener("click", function() {
                    var btn = this.parentElement.querySelector(".copy-btn");
                    if (btn) copyText(this.id, btn);
                });
            });
        </script>
    </body>
    </html>';
}

// ---- Main Routing ----
$requestUri   = $_SERVER['REQUEST_URI'];
$userAgent    = $_SERVER['HTTP_USER_AGENT'] ?? '';
$acceptHeader = $_SERVER['HTTP_ACCEPT'] ?? '';

// ============ مسیر تک‌اشتراکی: /sub/single/{token} ============
if (preg_match('#^/sub/single/([a-zA-Z0-9]+)#', $requestUri, $matches)) {
    $token = $matches[1];
    $isBrowser = is_real_browser($userAgent, $acceptHeader);

    if ($isBrowser) {
        [$httpCode, $body, $err] = fetch_api('/sub/single/' . urlencode($token) . '?details=1');

        if ($err || $httpCode !== 200) {
            http_response_code($httpCode ?: 502);
            echo "❌ Error fetching subscription information" . ($err ? ": $err" : " (HTTP $httpCode)");
            exit;
        }

        $data = json_decode($body, true);
        if (!$data || empty($data['subscription'])) {
            http_response_code(502);
            echo "❌ Invalid response from subscription service";
            exit;
        }

        render_html_page($data['user_id'] ?? 'Unknown', [$data['subscription']]);
        exit;
    }

    // VPN Client Mode
    [$httpCode, $body, $err] = fetch_api('/sub/single/' . urlencode($token));

    if ($err || $httpCode !== 200) {
        http_response_code($httpCode ?: 502);
        echo "Subscription error" . ($err ? ": $err" : " (HTTP $httpCode)");
        exit;
    }

    header('Content-Type: text/plain; charset=utf-8');
    header('Content-Disposition: inline; filename="subscribe.txt"');
    echo $body;
    exit;
}

// ============ مسیر ترکیبی (تمام طرح‌ها): /sub/{token} ============
if (preg_match('#^/sub/([a-zA-Z0-9]+)#', $requestUri, $matches)) {
    $token = $matches[1];
    $isBrowser = is_real_browser($userAgent, $acceptHeader);

    if ($isBrowser) {
        [$httpCode, $body, $err] = fetch_api('/sub/' . urlencode($token) . '?details=1');

        if ($err || $httpCode !== 200) {
            http_response_code($httpCode ?: 502);
            echo "❌ Error fetching subscription information" . ($err ? ": $err" : " (HTTP $httpCode)");
            exit;
        }

        $data = json_decode($body, true);
        if (!$data) {
            http_response_code(502);
            echo "❌ Invalid response from subscription service";
            exit;
        }

        render_html_page($data['user_id'] ?? 'Unknown', $data['subscriptions'] ?? []);
        exit;
    }

    [$httpCode, $body, $err] = fetch_api('/sub/' . urlencode($token));

    if ($err || $httpCode !== 200) {
        http_response_code($httpCode ?: 502);
        echo "Subscription error" . ($err ? ": $err" : " (HTTP $httpCode)");
        exit;
    }

    header('Content-Type: text/plain; charset=utf-8');
    header('Content-Disposition: inline; filename="subscribe.txt"');
    echo $body;
    exit;
}

echo "✅ Subscription proxy is active.<br>Use <b>/sub/YOUR_TOKEN</b> or <b>/sub/single/YOUR_TOKEN</b>.";
