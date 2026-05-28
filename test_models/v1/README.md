# Test Model v1

This folder contains a small regression model and dataset used for testing the model upload and prediction pipeline.

## Contents
- data.csv: 50-row dataset with 3 features and a target.
- model.pkl: Trained scikit-learn LinearRegression model.
- model.yaml: Manifest for the model package.
- requirements.txt: Runtime dependencies for the model.
- schema.json: Request payload schema for inference.
- train_model.ipynb: Notebook to recreate the dataset and model.

## Rebuild the model
Open train_model.ipynb and run all cells. It will regenerate data.csv and model.pkl.

## Zip for upload
From repo root:

zip -r test_models/v1/test_model_v1.zip test_models/v1 \
  -x "*/__pycache__/*" "*.ipynb_checkpoints/*"
