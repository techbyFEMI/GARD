from fastapi.middleware.cors import CORSMiddleware

app.middleware(
  CORSMiddleware,
  allow_origin=["*"],
  allow_methods=["*"],
  allow_headers=["*"]
)
