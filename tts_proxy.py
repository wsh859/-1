"""
方言译 代理服务器
- TTS：调用阿里云 Qwen3-TTS 生成音频
- 翻译：调用 DeepSeek AI 翻译方言⇄普通话
用法：python tts_proxy.py
云端部署：设置环境变量 DASHSCOPE_KEY 和 DEEPSEEK_KEY
"""

import http.server
import json
import urllib.request
import os
import sys

# ── API Keys（优先从环境变量读取，本地可直接填写） ──
DASHSCOPE_KEY = os.environ.get('DASHSCOPE_KEY', 'sk-30f55952044943ac8e66d9410ef4a3ec')
DEEPSEEK_KEY  = os.environ.get('DEEPSEEK_KEY',  'sk-86816cac8fb14e089eb950089fb850f9')

# ── 端口（Render 会自动注入 PORT 环境变量） ──
PORT = int(os.environ.get('PORT', 8765))

# ── 阿里云 TTS ──
TTS_URL = 'https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation'

# ── DeepSeek 翻译 ──
DEEPSEEK_URL = 'https://api.deepseek.com/chat/completions'


def call_deepseek_translate(text, direction, dialect):
    """调用 DeepSeek 翻译"""

    if dialect == 'teochew':
        if direction == 'dialect_to_mandarin':
            prompt = (
                '你是潮汕话（潮州话）翻译专家。请将以下潮汕话翻译成标准普通话。\n'
                '注意：潮汕话用字可能包含：汝（你）、伊（他/她）、孥囝（小孩）、'
                '物件（东西）、底块（哪里）、乜个（什么）、猛猛（赶紧）、返内（回家）、'
                '食（吃）、饮（喝）、行（走）、走（跑）、雅（好/漂亮）、'
                '僫势（倒霉/难）、今仔（今天）、暗夜/夜昏（晚上）、街市（市场）、'
                '物配（菜/配菜）、耍（玩）、诚（很）等。\n'
                '只输出普通话翻译结果，不要解释：\n' + text
            )
        else:
            prompt = (
                '你是潮汕话（潮州话）翻译专家。请将以下普通话翻译成潮汕话。\n'
                '重要规则：\n'
                '1. 必须使用潮汕话特有写法，不要用粤语写法\n'
                '2. 常用字对照：你→汝、他/她→伊、小孩→孥囝、东西→物件、'
                '哪里→底块、什么→乜个、赶紧→猛猛、回家→返内、'
                '吃→食、喝→饮、走→行、跑→走、好/漂亮→雅、'
                '今天→今仔、晚上→暗夜、市场→街市、菜→物配、'
                '玩→耍、很→诚、我们→俺、了→了/掉\n'
                '3. 不要出现粤语用字：唔使、我哋、呢個、返屋企、細路等\n'
                '4. 用简体字书写\n'
                '只输出潮汕话翻译结果，不要解释：\n' + text
            )
    else:
        # 粤语
        if direction == 'dialect_to_mandarin':
            prompt = f'请将以下粤语（广东话）翻译成标准普通话，只输出翻译结果，不要解释：\n{text}'
        else:
            prompt = (
                '请将以下普通话翻译成粤语（广东话）。\n'
                '使用常见粤语写法：你→你、他/她→佢、东西→嘢、什么→乜/咩、'
                '没有→冇、了→咗、在→喺、和→同、的→嘅、吧→啦、'
                '小孩→细路/BB、吃饭→食饭、回家→返屋企、我们→我哋\n'
                '只输出粤语翻译结果，不要解释：\n' + text
            )

    data = json.dumps({
        'model': 'deepseek-chat',
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.3,
        'max_tokens': 1024
    }).encode('utf-8')

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {DEEPSEEK_KEY}'
    }

    req = urllib.request.Request(DEEPSEEK_URL, data=data, headers=headers, method='POST')
    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read())

    return result['choices'][0]['message']['content'].strip()


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if self.path == '/ping':
            self.send_json(200, {'status': 'ok'})
        else:
            self.send_json(404, {'error': 'not found'})

    def do_POST(self):
        if self.path == '/tts':
            self.handle_tts()
        elif self.path == '/translate':
            self.handle_translate()
        else:
            self.send_json(404, {'error': 'not found'})

    def handle_tts(self):
        """TTS 语音合成"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            params = json.loads(body)
            text = params.get('text', '').strip()
            voice = params.get('voice', 'Roy')

            if not text:
                self.send_json(400, {'error': 'text is empty'})
                return

            # 调用阿里云 Qwen3-TTS
            api_data = json.dumps({
                'model': 'qwen3-tts-flash',
                'input': {
                    'text': text,
                    'voice': voice,
                    'language_type': 'Chinese'
                }
            }).encode()

            api_headers = {
                'Authorization': f'Bearer {DASHSCOPE_KEY}',
                'Content-Type': 'application/json'
            }

            req = urllib.request.Request(TTS_URL, data=api_data, headers=api_headers, method='POST')
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read())

            audio_url = result.get('output', {}).get('audio', {}).get('url', '')

            if not audio_url:
                self.send_json(500, {'error': 'no audio url returned'})
                return

            # 下载音频数据
            audio_req = urllib.request.Request(audio_url)
            audio_resp = urllib.request.urlopen(audio_req, timeout=30)
            audio_data = audio_resp.read()

            # 返回音频
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'audio/wav')
            self.send_header('Content-Length', str(len(audio_data)))
            self.end_headers()
            self.wfile.write(audio_data)

            print(f'  [TTS] "{text[:20]}..." -> {len(audio_data)} bytes')

        except Exception as e:
            print(f'  [TTS ERROR] {e}')
            self.send_json(500, {'error': str(e)})

    def handle_translate(self):
        """DeepSeek AI 翻译"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            params = json.loads(body)
            text = params.get('text', '').strip()
            direction = params.get('direction', 'dialect_to_mandarin')
            dialect = params.get('dialect', 'cantonese')

            if not text:
                self.send_json(400, {'error': 'text is empty'})
                return

            result = call_deepseek_translate(text, direction, dialect)

            self.send_json(200, {'result': result})
            print(f'  [翻译] "{text[:20]}..." -> "{result[:20]}..."')

        except Exception as e:
            print(f'  [翻译 ERROR] {e}')
            self.send_json(500, {'error': str(e)})

    def send_json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # 静默日志


if __name__ == '__main__':
    # 监听 0.0.0.0（云端部署必须，本地也兼容）
    server = http.server.HTTPServer(('0.0.0.0', PORT), ProxyHandler)
    print(f'')
    print(f'  ========================================')
    print(f'   方言译 代理服务器已启动')
    print(f'   地址: http://0.0.0.0:{PORT}')
    print(f'   功能: AI翻译 + 方言语音播报')
    print(f'   按 Ctrl+C 停止')
    print(f'  ========================================')
    print(f'')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n  服务器已停止')
        server.server_close()
