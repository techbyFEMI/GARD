from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
  CORSMiddleware,
  allow_origins=[
  "https://gardfrontend.vercel.app"
  "https://gardfrontend.vercel.app/index2.html"
  ],
  allow_methods=["*"],
  allow_headers=["*"]
)
