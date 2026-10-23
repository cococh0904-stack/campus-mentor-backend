
import os

from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai

app = Flask(__name__)

# 只允許你的 GitHub Pages 網站呼叫 API
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                "https://cococh0904-stack.github.io"
            ]
        }
    }
)

API_KEY = os.environ.get("GEMINI_API_KEY")

if API_KEY:
    client = genai.Client(api_key=API_KEY)
else:
    client = None

MODEL = "gemini-3.8-flash"


@app.route("/")
def home():
    return "AI 校園導師小幫手後端運作中！"


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "model": MODEL,
        "api_key_configured": client is not None
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    if client is None:
        return jsonify({
            "error": "後端尚未設定 Gemini API 金鑰。"
        }), 500

    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()

    if not message:
        return jsonify({"error": "請先輸入問題。"}), 400

    if len(message) > 3000:
        return jsonify({"error": "問題太長，請縮短後再試。"}), 400

    history = data.get("history", [])
    if not isinstance(history, list):
        history = []

    previous = []
    for item in history[-8:]:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = item.get("content")

        if role in ("user", "model") and isinstance(content, str):
            previous.append(f"{role}: {content[:1000]}")

    prompt = f"""
你是 AI 校園導師小幫手，使用繁體中文，回答要友善、清楚，
並適合大學生理解。

你可以協助課業、Python 程式、校園生活、選課及生涯規劃。
遇到亞洲大學的課程、學分或畢業規定時，優先查找官方資料。
不確定的資訊必須說明，不可捏造規定或來源。

先前對話：
{chr(10).join(previous)}

學生本次問題：
{message}
"""

    try:
        result = client.interactions.create(
            model=MODEL,
            input=prompt,
            tools=[{"type": "google_search"}],
            generation_config={"thinking_level": "low"}
        )

        reply = getattr(result, "output_text", None)
        if not reply:
            reply = "抱歉，這次沒有取得文字回答。"

        sources = []
        seen = set()

        # 嘗試取得搜尋引用；若模型沒有提供引用，仍可正常回答
        for item in (getattr(result, "outputs", None) or []):
            for annotation in (
                getattr(item, "annotations", None) or []
            ):
                url = getattr(annotation, "url", None)
                title = getattr(annotation, "title", None) or url

                if (
                    url
                    and url.startswith("https://")
                    and url not in seen
                ):
                    seen.add(url)
                    sources.append({
                        "title": title,
                        "url": url
                    })

        if any(k in message for k in [
            "亞洲大學", "選課", "畢業", "課程", "學分"
        ]):
            official = [
                {
                    "title": "亞洲大學人工智慧學系",
                    "url": "https://aiau.asia.edu.tw/"
                },
                {
                    "title": "亞洲大學官方網站",
                    "url": "https://www.asia.edu.tw/"
                }
            ]

            for source in official:
                if source["url"] not in seen:
                    sources.append(source)

        return jsonify({
            "reply": reply,
            "sources": sources[:8]
        })

    except Exception as e:
        # 詳細錯誤只記錄在伺服器日誌，不暴露金鑰
        app.logger.exception("Gemini API 呼叫失敗")
        return jsonify({
            "error": "AI 暫時無法回覆，請稍後再試。"
        }), 502
