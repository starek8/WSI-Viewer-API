from fastapi import FastAPI
from fastapi.responses import HTMLResponse

def create_app() -> FastAPI:
    app = FastAPI(title="WSI Viewer API")

    @app.get("/", response_class=HTMLResponse)
    def root():
        html_content = """
        <html>
            <head>
                <title>WSI Viewer</title>
                <style>
                    body { font-family: Arial, sans-serif; background-color: #f4f4f4; color: #333; text-align: center; padding: 50px; }
                    h1 { color: #2c3e50; }
                    p { font-size: 18px; }
                    .button { background-color: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }
                    .button:hover { background-color: #2980b9; }
                </style>
            </head>
            <body>
                <h1>Welcome to the WSI Viewer API</h1>
                <p>This is your starting point for serving WSI images.</p>
                <a class="button" href="/docs">API Documentation</a>
            </body>
        </html>
        """
        return html_content

    return app
