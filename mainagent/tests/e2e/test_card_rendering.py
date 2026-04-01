"""卡片渲染 E2E 测试 — 验证 ```spec 围栏在浏览器中正确渲染为卡片组件。

使用 mock SSE 服务器返回固定的 spec fence 内容，Playwright 验证卡片渲染。
"""

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

# 路径
PROJECT_ROOT = Path(__file__).resolve().parents[3]
MAINAGENT_DIR = PROJECT_ROOT / "mainagent"
WEB_DIR = PROJECT_ROOT / "web"
DIST_DIR = WEB_DIR / "dist"

MOCK_PORT = 8197


# ── Mock SSE Server ──

MOCK_RESPONSES = {
    "shop_cards": {
        "text_events": [
            "为您找到3家商家，按价格排序：\n\n",
            "```spec\n",
            '{"type":"ShopCard","props":{"name":"张江汽修中心","price":500,"rating":4.8,"distance":"2.3km"}}\n',
            '{"type":"ShopCard","props":{"name":"浦东养车坊","price":520,"rating":4.6,"distance":"3.1km"}}\n',
            '{"type":"ShopCard","props":{"name":"陆家嘴汽服","price":580,"rating":4.9,"distance":"1.2km"}}\n',
            "```\n\n",
            "最低价是张江汽修中心500元，需要帮您预约吗？",
        ]
    },
    "mixed_cards": {
        "text_events": [
            "为您找到最优方案：\n\n",
            "```spec\n",
            '{"type":"ShopCard","props":{"name":"张江汽修中心","price":500,"rating":4.8,"distance":"2.3km"}}\n',
            '{"type":"CouponCard","props":{"shop_id":1,"shop_name":"张江汽修中心","activity_id":101,"activity_name":"新客立减50元"}}\n',
            "```\n\n",
            "使用优惠券后实付450元。",
        ]
    },
    "project_card": {
        "text_events": [
            "更换刹车片报价如下：\n\n",
            "```spec\n",
            '{"type":"ProjectCard","props":{"name":"更换前刹车片","laborFee":200,"partsFee":380,"totalPrice":580,"duration":"1.5小时"}}\n',
            "```\n\n",
            "以上是博世刹车片的报价。",
        ]
    },
}


def _make_mock_server_script() -> str:
    """生成 mock SSE 服务器的 Python 脚本内容"""
    return f'''
import json, asyncio
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

app = FastAPI()
DIST = Path("{DIST_DIR}")
RESPONSES = {json.dumps(MOCK_RESPONSES)}

@app.post("/chat/stream")
async def chat_stream(request: Request):
    body = await request.json()
    msg = body.get("message", "")

    # 根据消息选择响应
    if "混合" in msg or "优惠" in msg:
        key = "mixed_cards"
    elif "项目" in msg or "报价" in msg:
        key = "project_card"
    else:
        key = "shop_cards"

    resp = RESPONSES[key]

    async def generate():
        # chat_request_start
        start = {{"session_id": body.get("session_id",""), "request_id": "mock-req", "type": "chat_request_start", "data": {{"task_id": "mock-task"}}}}
        yield f"event: chat_request_start\\ndata: {{json.dumps(start)}}\\n\\n"
        await asyncio.sleep(0.05)

        # text events
        for chunk in resp["text_events"]:
            evt = {{"session_id": body.get("session_id",""), "request_id": "mock-req", "type": "text", "data": {{"content": chunk}}}}
            yield f"event: text\\ndata: {{json.dumps(evt)}}\\n\\n"
            await asyncio.sleep(0.02)

        # chat_request_end
        end = {{"session_id": body.get("session_id",""), "request_id": "mock-req", "type": "chat_request_end", "data": {{}}}}
        yield f"event: chat_request_end\\ndata: {{json.dumps(end)}}\\n\\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/health")
async def health():
    return {{"status": "ok"}}

# Serve frontend static files
if DIST.exists():
    app.mount("/", StaticFiles(directory=str(DIST), html=True))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port={MOCK_PORT})
'''


@pytest.fixture(scope="module")
def card_server_url():
    """启动 mock SSE + 静态文件服务器"""
    # Build frontend if needed
    if not DIST_DIR.exists():
        subprocess.run(["npx", "vite", "build"], cwd=str(WEB_DIR), check=True, timeout=60)

    # Write mock server script
    script = Path("/tmp/card_mock_server.py")
    script.write_text(_make_mock_server_script())

    proc = subprocess.Popen(
        [sys.executable, str(script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    url = f"http://127.0.0.1:{MOCK_PORT}"

    # Wait for health
    import httpx
    for _ in range(30):
        try:
            r = httpx.get(f"{url}/health", timeout=2)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        proc.kill()
        pytest.fail("Mock server failed to start")

    yield url

    proc.kill()
    proc.wait()


@pytest.fixture
def chat_page(page: Page, card_server_url: str) -> Page:
    page.goto(card_server_url)
    page.wait_for_selector("#input-box")
    return page


class TestCardRendering:
    """验证 ```spec 围栏在浏览器中渲染为卡片"""

    def test_shop_cards_render(self, chat_page: Page) -> None:
        """ShopCard × 3 正确渲染"""
        page = chat_page

        page.locator("#input-box").fill("帮我找商家")
        page.locator("#send-btn").click()

        # 等待 agent 回复完成
        page.wait_for_selector("#send-btn", timeout=10000)

        # 应有 3 个 ShopCard
        shop_cards = page.locator(".shop-card")
        expect(shop_cards).to_have_count(3)

        # 第一个卡片内容正确
        first_card = shop_cards.first
        expect(first_card).to_contain_text("张江汽修中心")
        expect(first_card).to_contain_text("500")
        expect(first_card).to_contain_text("4.8")

        # 卡片前后有文字
        text_segment = page.locator(".text-segment").last
        expect(text_segment).to_contain_text("为您找到3家商家")
        expect(text_segment).to_contain_text("需要帮您预约吗")

    def test_mixed_cards_render(self, chat_page: Page) -> None:
        """ShopCard + CouponCard 混合渲染"""
        page = chat_page

        page.locator("#input-box").fill("帮我找商家和优惠券")
        page.locator("#send-btn").click()
        page.wait_for_selector("#send-btn", timeout=10000)

        # 应有 1 个 ShopCard + 1 个 CouponCard
        expect(page.locator(".shop-card")).to_have_count(1)
        expect(page.locator(".coupon-card")).to_have_count(1)

        # CouponCard 内容
        coupon = page.locator(".coupon-card")
        expect(coupon).to_contain_text("张江汽修中心")
        expect(coupon).to_contain_text("新客立减50元")

    def test_project_card_render(self, chat_page: Page) -> None:
        """ProjectCard 报价卡片渲染"""
        page = chat_page

        page.locator("#input-box").fill("更换刹车片报价")
        page.locator("#send-btn").click()
        page.wait_for_selector("#send-btn", timeout=10000)

        # 应有 1 个 ProjectCard
        project = page.locator(".project-card")
        expect(project).to_have_count(1)
        expect(project).to_contain_text("更换前刹车片")
        expect(project).to_contain_text("580")
        expect(project).to_contain_text("1.5小时")

    def test_no_raw_spec_fence_visible(self, chat_page: Page) -> None:
        """spec 围栏语法不应出现在渲染结果中"""
        page = chat_page

        page.locator("#input-box").fill("帮我找商家")
        page.locator("#send-btn").click()
        page.wait_for_selector("#send-btn", timeout=10000)

        text = page.locator(".text-segment").last.inner_text()
        assert "```spec" not in text
        assert "```" not in text
        assert '"type"' not in text
