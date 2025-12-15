import joblib 

def load_congestion_model():
    model = joblib.load("congestion_duration_model.pkl")
    return model

def predict_congestion_duration(model, X):
    prediction = model.predict(X)
    return prediction