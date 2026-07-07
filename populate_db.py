import os
import django
import random
import uuid
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model
from model_registry.models import Model, ModelVersion
from billing.models import Wallet

User = get_user_model()

DEVELOPERS = [
    ("alice_data", "Alice Wonderland"),
    ("bob_ml", "Bob Builder"),
    ("charlie_vision", "Charlie Chaplin"),
    ("dana_nlp", "Dana Scully"),
    ("eve_ai", "Eve Hacker"),
]

MODELS = [
    {
        "name": "sentiment-analysis", 
        "framework": "sklearn", 
        "task": "classification", 
        "cost": 0.0010, 
        "desc": "A fast robust sentiment analyzer based on Logistic Regression.",
        "readme": """# Sentiment Analysis Classifier
This is a lightweight logistic regression model trained on 500,000 IMDB movie reviews. It predicts whether a given text snippet has a positive or negative sentiment.

## Input Schema
Send a JSON array containing a single string (the text to analyze):
```json
{
  "features": [["This movie was absolutely fantastic, I loved the acting!"]]
}
```

## Output
Returns a classification label (`POSITIVE` or `NEGATIVE`) and a confidence score.

### Performance
- **Accuracy**: 89.4%
- **F1 Score**: 0.88
- **Latency**: ~12ms
"""
    },
    {
        "name": "yolo-v8-tiny", 
        "framework": "pytorch", 
        "task": "object-detection", 
        "cost": 0.0050, 
        "desc": "Tiny YOLOv8 implementation for real-time edge devices.",
        "readme": """# YOLOv8 Tiny (PyTorch)
Real-time object detection model capable of identifying 80 distinct COCO object classes. The 'tiny' variant sacrifices a small amount of accuracy for a massive speedup, making it ideal for edge inference.

## Input Schema
The model expects a base64 encoded image or a normalized tensor. For the API, provide flattened normalized pixel values `[1, 3, 416, 416]`.

```json
{
  "features": [[[0.5, 0.5, ...]]]
}
```

## Supported Classes
Person, Bicycle, Car, Motorcycle, Airplane, Bus, Train, Truck, Boat, Traffic light, ...
"""
    },
    {
        "name": "resnet50-feature-extractor", 
        "framework": "pytorch", 
        "task": "feature-extraction", 
        "cost": 0.0025, 
        "desc": "Standard ResNet50 initialized with ImageNet weights, headless.",
        "readme": """# ResNet-50 Feature Extractor
This model is the classic ResNet-50 architecture with the final classification head removed. It takes an image and outputs a 2048-dimensional feature embedding. 

Use this model for building search engines, image similarity databases, or downstream classification tasks.

## Input Schema
Provide an array of normalized pixel tensors (shape `[N, 3, 224, 224]`).

## Output Schema
Returns an array of embeddings: `[N, 2048]`.
"""
    },
    {
        "name": "churn-predictor", 
        "framework": "sklearn", 
        "task": "regression", 
        "cost": 0.0005, 
        "desc": "Random Forest model to predict SaaS customer churn probability.",
        "readme": """# SaaS Churn Predictor
A Scikit-Learn Random Forest model that predicts the likelihood of a SaaS customer canceling their subscription within the next 30 days.

## Input Schema
Provide a numerical array of 12 customer metrics:
1. Days since last login
2. Total sessions (last 30d)
3. Total active minutes
4. Support tickets opened
5. ... etc

```json
{
  "features": [[14, 5, 120, 1, 0, 0, 1, 0.5, 99.9, 12, 1, 0]]
}
```

## Output
Returns a float between `0.0` (will not churn) and `1.0` (highly likely to churn).
"""
    },
    {
        "name": "text-summarizer", 
        "framework": "pytorch", 
        "task": "text2text", 
        "cost": 0.0120, 
        "desc": "BART-large based summarization model finetuned on CNN/DailyMail.",
        "readme": """# Text Summarization (BART Large)
Finetuned on the CNN/DailyMail dataset, this model takes a long article and produces a concise, abstractive summary.

> **Note:** This is a heavy model and runs on GPU infrastructure, so the cost per run is slightly higher.

## Input Schema
```json
{
  "features": [["Large block of text goes here..."]]
}
```

## Output Schema
A short paragraph summarizing the input.
"""
    },
    {
        "name": "iris-classifier", 
        "framework": "sklearn", 
        "task": "classification", 
        "cost": 0.0001, 
        "desc": "The classic Iris dataset classifier using SVM.",
        "readme": """# Hello World: Iris Classifier
The classic introductory machine learning model! This uses a Support Vector Machine (SVM) to classify Iris flowers into three species based on their sepal and petal dimensions.

## Input Features
1. Sepal Length (cm)
2. Sepal Width (cm)
3. Petal Length (cm)
4. Petal Width (cm)

```json
{
  "features": [[5.1, 3.5, 1.4, 0.2]]
}
```

## Classes
- 0: Setosa
- 1: Versicolor
- 2: Virginica
"""
    }
]

def run():
    print("Repopulating database with rich markdown...")
    
    # First delete existing dummy models to prevent duplicates
    Model.objects.all().delete()
    print("Cleared existing models.")

    for username, full_name in DEVELOPERS:
        # Create user
        email = f"{username}@example.com"
        user, created = User.objects.get_or_create(username=username, defaults={"email": email})
        if created:
            user.set_password("password123")
            user.save()
        
        # Ensure wallet exists
        Wallet.objects.get_or_create(user=user)
        
        # Pick 2-4 random models for this user
        num_models = random.randint(2, 4)
        selected_models = random.sample(MODELS, num_models)
        
        for m_data in selected_models:
            # Create model
            model = Model.objects.create(
                id=str(uuid.uuid4()),
                owner=user,
                name=m_data["name"],
                framework=m_data["framework"],
                task_type=m_data["task"],
                is_public=True,
                cost_per_run=Decimal(str(m_data["cost"])),
                description=m_data["desc"],
                readme_markdown=m_data["readme"]
            )
            
            # Create at least one version
            ModelVersion.objects.create(
                model=model,
                version="v1.0.0",
                artifact_path=f"s3://model-bucket/{username}/{model.name}/v1/",
                status="READY"
            )
            print(f"  -> Created rich model {model.name} for @{username}")

    print("Done populating!")

if __name__ == "__main__":
    run()
