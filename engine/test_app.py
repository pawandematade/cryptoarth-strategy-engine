from fastapi import FastAPI

app = FastAPI(
    title="CryptoArth Strategy Engine",
    version="1.0.0",
    description="Trading Strategy Engine API"
)

@app.get("/")
async def root():
    return {"status": "ok", "service": "CryptoArth Strategy Engine"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/api/strategy/test")
async def test_strategy():
    return {"message": "Strategy engine working"}
