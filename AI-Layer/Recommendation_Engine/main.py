from fastapi import FastAPI
import pandas as pd
from graph_builder import build_social_graph
from recommender import recommend

app = FastAPI()

orders_df = pd.read_csv("orders.csv")
restaurants_df = pd.read_csv("restaurants.csv")
graph = build_social_graph(orders_df)

@app.get("/recommend/{user_id}")
def get_recommendations(user_id: int):
    recs = recommend(user_id, graph, orders_df, restaurants_df)
    return {"recommendations": recs}