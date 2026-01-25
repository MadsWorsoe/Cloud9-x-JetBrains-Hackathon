import tensorflow as tf
from tensorflow.keras import layers, models


def build_model(num_features: int):
    model = models.Sequential([
        layers.Input(shape=(num_features,)),
        layers.Dense(64, activation="relu"),
        layers.Dense(32, activation="relu"),
        layers.Dense(1, activation="sigmoid"),
    ])

    model.compile(
        optimizer="adam",
        loss="binary_crossentropy",
        metrics=[
            "accuracy",
            tf.keras.metrics.AUC(name="auc"),
        ]
    )
    return model
