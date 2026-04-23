import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / '.env')

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrderActivitiesRequest
from alpaca.trading.enums import ActivityType

trading_client = TradingClient(os.getenv("APCA_API_KEY_ID"), os.getenv("APCA_API_SECRET_KEY"), paper=True)

req = GetOrderActivitiesRequest(activity_types=[ActivityType.FILL])
activities = trading_client.get_account_activities(req)

print("Recent Alpaca Fills:")
for act in activities[:5]:
    print(f"Date: {act.transaction_time}, Symbol: {act.symbol}, Side: {act.side}, Qty: {act.qty}, Price: {act.price}")
