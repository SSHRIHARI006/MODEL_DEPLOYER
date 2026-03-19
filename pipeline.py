from sklearn.linear_model import LinearRegression
import joblib

model = LinearRegression()
model.fit([[1], [2], [3]], [2, 4, 6])

joblib.dump(model, "model.pkl")