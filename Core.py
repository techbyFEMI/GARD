from fastapi.middleware.cors import CORSMiddleware

app.middleware(
  CORSMiddleware,
  settings.add_origin,
  "https://gardfrontend.vercel.app"
  "https://gardfrontend.vercel.app/index2.html"
  allow_methods=["*"],
  allow_headers=["*"]
)
