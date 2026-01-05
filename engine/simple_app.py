from fastapi import FastAPI

app = FastAPI(
    title="CryptoArth Strategy Engine",
    version="1.0.0"
)

@app.get("/")
async def root():
    return {"status": "ok", "service": "Strategy Engine"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/api/strategy/test")
async def test():
    return {"message": "Strategy endpoint working"}
