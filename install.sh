<?php
// ==========================================================
// پروکسی اشتراک - با پشتیبانی از اسپانسر و نمایش کانفیگ‌ها
// برای استفاده با sub_api.py روی سرور اصلی
// ==========================================================

// ========== تنظیمات ==========
define('API_BASE', 'http://127.0.0.1:8088');  // آدرس sub_api.py (اگر روی همین سرور نیست، IP واقعی را بزنید)
define('API_KEY', '');  // اگر در sub_api.py API_KEY تنظیم کرده‌اید، اینجا هم قرار دهید

// ========== توابع کمکی ==========
function get_api_key() {
    return API_KEY ?: '';
}

function call_api($endpoint, $token, $params = []) {
    $url = API_BASE . $endpoint . '/' . $token;
    if (!empty($params)) {
        $url .= '?' . http_build_query($params);
    }
    
    $ch = curl_init();
    curl_setopt($ch, CURLOPT_URL, $url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 15);
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
    curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, false);
    
    $api_key = get_api_key();
    if (!empty($api_key)) {
        curl_setopt($ch, CURLOPT_HTTPHEADER, ['X-API-Key: ' . $api_key]);
    }
    
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode !== 200) {
        return null;
    }
    
    return json_decode($response, true);
}

function render_subscription_html($subscriptions, $user_id) {
    $html = '<div class="sub-container">';
    $html .= '<div class="header">';
    $html .= '<h2>🔗 لینک‌های اشتراک شما</h2>';
    $html .= '<p>شناسه کاربر: <code>' . htmlspecialchars($user_id) . '</code></p>';
    $html .= '</div>';
    
    if (empty($subscriptions)) {
        $html .= '<div class="empty">';
        $html .= '⚠️ هیچ اشتراک فعالی ندارید.';
        $html .= '</div>';
    } else {
        foreach ($subscriptions as $sub) {
            $plan_name = htmlspecialchars($sub['plan_name'] ?? 'پلن');
            $panel_name = htmlspecialchars($sub['panel_name'] ?? 'پنل');
            $remaining = isset($sub['remaining_volume']) ? $sub['remaining_volume'] . ' گیگ' : 'نامحدود';
            $end_date = $sub['end_date'] ?? 'نامشخص';
            $email = htmlspecialchars($sub['email'] ?? '');
            
            $html .= '<div class="sub-item">';
            $html .= '<div class="sub-info">';
            $html .= '<div class="sub-title">📦 ' . $plan_name . '</div>';
            $html .= '<div class="sub-meta">';
            $html .= '<span>🖥 ' . $panel_name . '</span>';
            $html .= '<span>📊 ' . $remaining . '</span>';
            $html .= '<span>📅 انقضا: ' . $end_date . '</span>';
            $html .= '</div>';
            
            if (!empty($email)) {
                $html .= '<div class="sub-email">📧 <code>' . $email . '</code></div>';
            }
            
            // نمایش لینک‌های کانفیگ
            if (!empty($sub['links'])) {
                $html .= '<div class="sub-links">';
                foreach ($sub['links'] as $idx => $link) {
                    $html .= '<div class="link-item">';
                    $html .= '<span class="link-num">' . ($idx + 1) . '.</span>';
                    $html .= '<code class="link-code">' . htmlspecialchars($link) . '</code>';
                    $html .= '<button class="copy-btn" onclick="copyToClipboard(\'' . htmlspecialchars(addslashes($link)) . '\')">📋 کپی</button>';
                    $html .= '</div>';
                }
                $html .= '</div>';
            } else {
                $html .= '<div class="no-links">⚠️ لینکی برای این اشتراک یافت نشد</div>';
            }
            
            $html .= '</div>';
            $html .= '</div>';
        }
    }
    
    $html .= '</div>';
    return $html;
}

// ========== پردازش درخواست ==========
$requestUri = $_SERVER['REQUEST_URI'] ?? '/';
$userAgent = $_SERVER['HTTP_USER_AGENT'] ?? '';
$isBrowser = preg_match('/(Chrome|Firefox|Safari|Opera|Edge|MSIE|Trident)/i', $userAgent);

// استخراج توکن از مسیر
if (preg_match('#^/sub/([a-zA-Z0-9_-]+)#', $requestUri, $matches)) {
    $token = $matches[1];
    
    // -------- حالت مرورگر (نمایش HTML) --------
    if ($isBrowser) {
        // دریافت اطلاعات کامل از API
        $data = call_api('/api/raw', $token);
        
        if (!$data) {
            http_response_code(404);
            echo '<h1>❌ اشتراک یافت نشد</h1>';
            echo '<p>لینک اشتراک نامعتبر است یا منقضی شده.</p>';
            exit;
        }
        
        $user_id = $data['user_id'] ?? 'نامشخص';
        $subscriptions = $data['subscriptions'] ?? [];
        
        // ========== رندر HTML کامل ==========
        header('Content-Type: text/html; charset=utf-8');
        
        ?>
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔗 لینک‌های اشتراک - جاده تونل</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Tahoma, sans-serif;
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
        .sub-links {
            margin-top: 12px;
        }
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
        .footer a {
            color: #6dd5fa;
            text-decoration: none;
            font-weight: 500;
        }
        .footer a:hover {
            text-decoration: underline;
        }
        .sponsor-badge {
            display: inline-block;
            background: rgba(167, 139, 250, 0.12);
            padding: 6px 18px;
            border-radius: 30px;
            font-size: 0.8rem;
            border: 1px solid rgba(167, 139, 250, 0.15);
        }
        .sponsor-badge a {
            color: #a78bfa;
            text-decoration: none;
        }
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
        .toast.show {
            opacity: 1;
        }
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
            <h2>🔗 لینک‌های اشتراک شما</h2>
            <p>شناسه کاربر: <code><?php echo htmlspecialchars($user_id); ?></code></p>
        </div>

        <?php echo render_subscription_html($subscriptions, $user_id); ?>

        <div class="footer">
            <div class="sponsor-badge">
                🌟 Sponsored by <a href="https://t.me/HeySoloATM" target="_blank">@HeySoloATM</a>
            </div>
            <div style="margin-top: 8px;">
                🔗 <a href="<?php echo htmlspecialchars($_SERVER['REQUEST_URI']); ?>" target="_blank">لینک اشتراک یکپارچه (برای Import)</a>
            </div>
        </div>
    </div>

    <div id="toast" class="toast">✅ کپی شد!</div>

    <script>
        function copyToClipboard(text) {
            navigator.clipboard.writeText(text).then(() => {
                const toast = document.getElementById('toast');
                toast.classList.add('show');
                setTimeout(() => toast.classList.remove('show'), 2000);
            }).catch(err => {
                // Fallback
                const input = document.createElement('textarea');
                input.value = text;
                document.body.appendChild(input);
                input.select();
                document.execCommand('copy');
                document.body.removeChild(input);
                const toast = document.getElementById('toast');
                toast.classList.add('show');
                setTimeout(() => toast.classList.remove('show'), 2000);
            });
        }

        // خودکار کپی روی کلیک لینک
        document.querySelectorAll('.link-code').forEach(el => {
            el.addEventListener('click', function() {
                copyToClipboard(this.textContent.trim());
            });
        });
    </script>
</body>
</html>
<?php
        exit;
    }
    
    // -------- حالت غیر مرورگر (Import در کلاینت) --------
    // دریافت لینک ساب به فرمت base64
    $api_url = API_BASE . '/sub/' . $token;
    $ch = curl_init();
    curl_setopt($ch, CURLOPT_URL, $api_url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 15);
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
    curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, false);
    curl_setopt($ch, CURLOPT_USERAGENT, 'PasarGuard-Proxy');
    
    $api_key = get_api_key();
    if (!empty($api_key)) {
        curl_setopt($ch, CURLOPT_HTTPHEADER, ['X-API-Key: ' . $api_key]);
    }
    
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode !== 200) {
        http_response_code($httpCode);
        die("❌ خطا در دریافت اشتراک: HTTP $httpCode");
    }
    
    header('Content-Type: text/plain; charset=utf-8');
    header('Content-Disposition: inline; filename="subscribe.txt"');
    echo $response;
    exit;
}

// ========== صفحه اصلی ==========
echo "✅ Subscription proxy is active. Use /sub/YOUR_TOKEN to get subscription.";
?>
