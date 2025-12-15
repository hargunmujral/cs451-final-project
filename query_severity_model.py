import joblib 

def load_severity_model():
    model = joblib.load("severity_model.pkl")
    return model

def predict_severity(model, X):
    prediction = model.predict(X)
    return prediction