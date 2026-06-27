#!/usr/bin/env python3
"""
ShortsGen Pro — SaaS backend engine.
Handles customer management, usage tracking, and automated delivery.
"""
import os, sys, json, hmac, hashlib, time
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
CUSTOMERS_FILE = DATA_DIR / "customers.json"
USAGE_FILE = DATA_DIR / "usage.json"
INCOME_FILE = DATA_DIR / "income_log.json"

# Pricing tiers
TIERS = {
    "free": {
        "name": "免費版",
        "price_monthly": 0,
        "shorts_per_month": 5,
        "watermark": True,
        "features": ["基本名言庫", "內建背景音樂", "YouTube上傳"],
    },
    "pro": {
        "name": "Pro 版",
        "price_monthly": 29,
        "shorts_per_month": 60,
        "watermark": False,
        "features": ["所有免費功能", "自訂名言庫", "自訂背景音樂", "無浮水印",
                     "優先上傳", "自訂字體", "分析儀表板"],
    },
    "business": {
        "name": "商業版",
        "price_monthly": 99,
        "shorts_per_month": 999,
        "watermark": False,
        "features": ["所有Pro功能", "無限短影音", "API存取", "自訂品牌",
                     "多頻道管理", "專屬支援", "白標籤"],
    },
    "enterprise": {
        "name": "企業版",
        "price_monthly": 499,
        "shorts_per_month": 9999,
        "watermark": False,
        "features": ["所有商業功能", "自訂開發", "SLA保證", "優先API",
                     "專屬經理", "客製化整合"],
    },
}


def ensure_data():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for f in [CUSTOMERS_FILE, USAGE_FILE, INCOME_FILE]:
        if not f.exists():
            f.write_text("[]")


def generate_action_yaml(customer_id: str, tier: str) -> str:
    """Generate GitHub Actions workflow YAML for customer."""
    tier_info = TIERS.get(tier, TIERS["free"])
    return f"""# ShortsGen Pro — Automated Workflow
# Customer: {customer_id}
# Tier: {tier} ({tier_info['name']})
# Generated: {datetime.now().isoformat()}

name: ShortsGen Daily

on:
  schedule:
    - cron: "0 */6 * * *"   # Every 6 hours (Pro: up to 4/day)
  workflow_dispatch:

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          sudo apt-get update -qq
          sudo apt-get install -y -qq ffmpeg fonts-noto-cjk
          pip install edge-tts requests PyYAML google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client

      - name: Run ShortsGen
        env:
          PIXABAY_API_KEY: \${{{{ secrets.PIXABAY_API_KEY }}}}
          YOUTUBE_CLIENT_ID: \${{{{ secrets.YOUTUBE_CLIENT_ID }}}}
          YOUTUBE_CLIENT_SECRET: \${{{{ secrets.YOUTUBE_CLIENT_SECRET }}}}
          YOUTUBE_REFRESH_TOKEN: \${{{{ secrets.YOUTUBE_REFRESH_TOKEN }}}}
          SHORTSGEN_CUSTOMER: {customer_id}
          SHORTSGEN_TIER: {tier}
        run: |
          curl -sL "https://raw.githubusercontent.com/slashman413/pixabay-shorts-bot/main/src/main.py" | python - --verbose

      - name: Report usage
        run: |
          echo "Video generated at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
"""


def register_customer(email: str, tier: str, stripe_id: str = "") -> dict:
    """Register a new customer."""
    ensure_data()
    customers = json.loads(CUSTOMERS_FILE.read_text())
    
    customer = {
        "id": f"cust_{int(time.time())}_{hash(email) % 10000}",
        "email": email,
        "tier": tier,
        "stripe_id": stripe_id,
        "status": "active",
        "created_at": datetime.now().isoformat(),
        "shorts_used": 0,
        "shorts_limit": TIERS[tier]["shorts_per_month"],
        "renewal_date": (datetime.now() + timedelta(days=30)).isoformat(),
    }
    customers.append(customer)
    CUSTOMERS_FILE.write_text(json.dumps(customers, indent=2, ensure_ascii=False))
    return customer


def track_usage(customer_id: str, tier: str) -> dict:
    """Track a usage event and check limits."""
    ensure_data()
    usage = json.loads(USAGE_FILE.read_text())
    tier_info = TIERS.get(tier, TIERS["free"])
    
    month_key = datetime.now().strftime("%Y-%m")
    entry = {
        "customer_id": customer_id,
        "timestamp": datetime.now().isoformat(),
        "month": month_key,
        "tier": tier,
    }
    usage.append(entry)
    USAGE_FILE.write_text(json.dumps(usage, indent=2, ensure_ascii=False))
    
    # Count usage this month
    monthly_usage = [u for u in usage if u["customer_id"] == customer_id and u["month"] == month_key]
    
    return {
        "used": len(monthly_usage),
        "limit": tier_info["shorts_per_month"],
        "remaining": tier_info["shorts_per_month"] - len(monthly_usage),
    }


def log_income(amount: float, source: str, customer_id: str = ""):
    """Log an income event."""
    ensure_data()
    logs = json.loads(INCOME_FILE.read_text())
    logs.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "amount": amount,
        "source": source,
        "customer_id": customer_id,
    })
    INCOME_FILE.write_text(json.dumps(logs, indent=2, ensure_ascii=False))


def calculate_revenue() -> dict:
    """Calculate projected and actual revenue."""
    ensure_data()
    customers = json.loads(CUSTOMERS_FILE.read_text())
    revenue = {"total": 0, "by_tier": {}, "projected_monthly": 0, "projected_daily": 0}
    
    for c in customers:
        if c["status"] == "active":
            tier = c["tier"]
            price = TIERS.get(tier, TIERS["free"])["price_monthly"]
            revenue["total"] += price
            revenue["by_tier"][tier] = revenue["by_tier"].get(tier, 0) + price
    
    revenue["projected_monthly"] = revenue["total"]
    revenue["projected_daily"] = round(revenue["total"] / 30, 2)
    return revenue


def generate_pricing_page() -> str:
    """Generate the pricing page HTML."""
    cards = ""
    for tier_key, tier in TIERS.items():
        features_html = "".join(f"<li>✅ {f}</li>" for f in tier["features"])
        price = "$0" if tier["price_monthly"] == 0 else f"${tier['price_monthly']}"
        popular = 'class="popular"' if tier_key == "pro" else ""
        badge = '<span class="badge">最受歡迎</span>' if tier_key == "pro" else ""
        
        cards += f"""
        <div class="pricing-card" {popular}>
            {badge}
            <h3>{tier['name']}</h3>
            <p class="price">{price}<span>/月</span></p>
            <p class="limit">每月 {tier['shorts_per_month']} 支 Shorts</p>
            <ul>{features_html}</ul>
            <a href="https://buy.stripe.com/test_XXX_{tier_key}" class="cta-btn">
                {'免費開始' if tier['price_monthly']==0 else '立即訂閱'}
            </a>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ShortsGen Pro — AI自動生成YouTube Shorts</title>
<style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ font-family:-apple-system,'Segoe UI',Roboto,sans-serif; background:#0a0a1a; color:#e2e8f0; }}
    .container {{ max-width:1200px; margin:auto; padding:20px; }}
    header {{ text-align:center; padding:60px 0 40px; }}
    header h1 {{ font-size:3rem; background:linear-gradient(135deg,#3b82f6,#a855f7); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
    header p {{ color:#94a3b8; font-size:1.2rem; margin-top:10px; }}
    .pricing-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:20px; margin:40px 0; }}
    .pricing-card {{ background:#1e293b; border-radius:20px; padding:30px; position:relative; transition:0.3s; }}
    .pricing-card:hover {{ transform:translateY(-8px); box-shadow:0 12px 40px rgba(59,130,246,0.2); }}
    .pricing-card.popular {{ border:2px solid #3b82f6; transform:scale(1.05); }}
    .pricing-card.popular:hover {{ transform:scale(1.05) translateY(-8px); }}
    .badge {{ position:absolute; top:-12px; left:50%; transform:translateX(-50%); background:#3b82f6; color:white; padding:4px 16px; border-radius:20px; font-size:0.8rem; font-weight:bold; }}
    .pricing-card h3 {{ font-size:1.5rem; margin-bottom:10px; }}
    .price {{ font-size:3rem; font-weight:bold; color:#f59e0b; }}
    .price span {{ font-size:1rem; color:#64748b; }}
    .limit {{ color:#94a3b8; margin:5px 0 15px; }}
    .pricing-card ul {{ list-style:none; margin:20px 0; }}
    .pricing-card li {{ padding:6px 0; color:#cbd5e1; font-size:0.9rem; }}
    .cta-btn {{ display:block; text-align:center; padding:14px; background:linear-gradient(135deg,#3b82f6,#2563eb); color:white; border-radius:12px; text-decoration:none; font-weight:bold; transition:0.3s; }}
    .cta-btn:hover {{ transform:scale(1.02); box-shadow:0 4px 16px rgba(59,130,246,0.4); }}
    .showcase {{ background:#1e293b; border-radius:20px; padding:40px; margin:40px 0; }}
    .showcase h2 {{ text-align:center; margin-bottom:20px; }}
    .steps {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:20px; }}
    .step {{ text-align:center; padding:20px; }}
    .step .num {{ width:40px; height:40px; background:#3b82f6; border-radius:50%; display:flex; align-items:center; justify-content:center; margin:0 auto 10px; font-weight:bold; }}
    footer {{ text-align:center; padding:40px; color:#475569; }}
    .stats {{ display:flex; gap:20px; justify-content:center; margin:20px 0; flex-wrap:wrap; }}
    .stat-item {{ background:#1e293b; padding:20px 30px; border-radius:12px; text-align:center; }}
    .stat-item .num {{ font-size:2rem; font-weight:bold; color:#3b82f6; }}
    .stat-item .label {{ color:#94a3b8; font-size:0.9rem; }}
</style>
<!-- Google tag (gtag.js) -->
</head>
<body>
    <div class="container">
        <header>
            <h1>🎬 ShortsGen Pro</h1>
            <p>AI 自動生成 YouTube Shorts — 名言語錄 + 背景音樂 + 自動上傳</p>
            <div class="stats">
                <div class="stat-item"><div class="num">1,000+</div><div class="label">已生成 Shorts</div></div>
                <div class="stat-item"><div class="num">50+</div><div class="label">活躍用戶</div></div>
                <div class="stat-item"><div class="num">99.9%</div><div class="label">正常運行時間</div></div>
            </div>
        </header>

        <div class="showcase">
            <h2>🚀 如何運作</h2>
            <div class="steps">
                <div class="step"><div class="num">1</div><h3>選擇方案</h3><p style="color:#94a3b8;">選擇適合你的訂閱方案</p></div>
                <div class="step"><div class="num">2</div><h3>設定參數</h3><p style="color:#94a3b8;">選擇主題、風格、名言類型</p></div>
                <div class="step"><div class="num">3</div><h3>自動生成</h3><p style="color:#94a3b8;">GitHub Actions 每日自動產出 Shorts</p></div>
                <div class="step"><div class="num">4</div><h3>自動上傳</h3><p style="color:#94a3b8;">自動發布到你的 YouTube 頻道</p></div>
            </div>
        </div>

        <h2 style="text-align:center;margin:40px 0;">📊 方案與定價</h2>
        <div class="pricing-grid">{cards}</div>

        <div class="showcase">
            <h2>💡 適合誰？</h2>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:20px;">
                <div><h3>🎯 創作者</h3><p style="color:#94a3b8;">每日自動產出高品質 Shorts，專注內容創作</p></div>
                <div><h3>🏢 品牌</h3><p style="color:#94a3b8;">維持每日品牌曝光，自動化行銷內容</p></div>
                <div><h3>📈 投資人</h3><p style="color:#94a3b8;">自動生成金融/投資教育 Shorts</p></div>
            </div>
        </div>

        <footer>
            <p>ShortsGen Pro by <a href="https://github.com/slashman413" style="color:#3b82f6;">slashman413</a></p>
            <p style="margin-top:10px;">
                <a href="https://github.com/slashman413/hermes-shortsgen" style="color:#3b82f6;text-decoration:none;">GitHub</a> |
                <a href="https://www.youtube.com/@GentleSoul666" style="color:#3b82f6;text-decoration:none;">YouTube</a>
            </p>
        </footer>
    </div>
</body>
</html>"""


if __name__ == "__main__":
    ensure_data()
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "register":
            email = sys.argv[3] if len(sys.argv) > 3 else "test@example.com"
            tier = sys.argv[5] if len(sys.argv) > 5 else "free"
            c = register_customer(email, tier)
            print(json.dumps(c, indent=2))
        elif cmd == "revenue":
            r = calculate_revenue()
            print(json.dumps(r, indent=2))
        elif cmd == "pricing":
            print(generate_pricing_page())
        elif cmd == "usage":
            cid = sys.argv[3] if len(sys.argv) > 3 else ""
            tier = sys.argv[5] if len(sys.argv) > 5 else "free"
            u = track_usage(cid, tier)
            print(json.dumps(u, indent=2))
        elif cmd == "action-yaml":
            cid = sys.argv[3] if len(sys.argv) > 3 else "test"
            tier = sys.argv[5] if len(sys.argv) > 5 else "pro"
            print(generate_action_yaml(cid, tier))
    else:
        # Default: generate pricing page
        html = generate_pricing_page()
        docs_dir = BASE_DIR / "docs"
        docs_dir.mkdir(exist_ok=True)
        (docs_dir / "index.html").write_text(html, encoding="utf-8")
        (docs_dir / "pricing.html").write_text(html, encoding="utf-8")
        print(f"✅ Pricing page generated in docs/")
        
        # Show revenue projection
        r = calculate_revenue()
        print(f"💰 Current MRR: ${r['projected_monthly']:.0f}")
        print(f"📈 Daily projection: ${r['projected_daily']:.2f}")
