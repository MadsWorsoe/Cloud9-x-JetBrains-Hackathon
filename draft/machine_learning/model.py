import tensorflow as tf
from tensorflow.keras import layers, models, Input

def build_draft_model(num_teams, num_champions, embedding_dim=16):
    # Inputs
    # Removed Team Inputs to prevent overfitting on Team Identity
    
    # Combined Picks Input (Sequence of 5)
    blue_picks_in = Input(shape=(5,), name="blue_picks") 
    red_picks_in = Input(shape=(5,), name="red_picks")
    blue_bans_in = Input(shape=(5,), name="blue_bans")
    red_bans_in = Input(shape=(5,), name="red_bans")
    
    stats_in = Input(shape=(12,), name="stats_features")

    # --- Embeddings ---
    champ_emb = layers.Embedding(num_champions, embedding_dim, name="champ_embedding")

    # --- Transformer Block (The Logic Engine) ---
    # We want to process the set of 5 picks and find internal conflicts/synergies
    
    def apply_transformer(input_layer):
        # 1. Embed: (Batch, 5) -> (Batch, 5, Dim)
        x = champ_emb(input_layer)
        
        # 2. Multi-Head Attention: "Look at other picks"
        # This is where it learns "If Jinx exists, Kog'Maw is bad"
        attn_output = layers.MultiHeadAttention(num_heads=2, key_dim=embedding_dim)(x, x)
        x = layers.Add()([x, attn_output]) # Residual connection
        x = layers.LayerNormalization()(x)
        
        # 3. Pool to vector: (Batch, 5, Dim) -> (Batch, Dim)
        return layers.GlobalAveragePooling1D()(x)

    # Apply Transformer to picks (most critical for synergy)
    bp_vec = apply_transformer(blue_picks_in)
    rp_vec = apply_transformer(red_picks_in)
    
    # Bans can use simpler pooling (order/synergy matters less for bans usually)
    bb_vec = layers.GlobalAveragePooling1D()(champ_emb(blue_bans_in))
    rb_vec = layers.GlobalAveragePooling1D()(champ_emb(red_bans_in))

    # Stats
    stats_vec = layers.Dense(32, activation='relu')(stats_in)

    # --- Final Interaction ---
    x = layers.Concatenate()([
        bp_vec, rp_vec, 
        bb_vec, rb_vec,
        stats_vec
    ])

    x = layers.Dense(64, activation='relu')(x)
    x = layers.Dropout(0.2)(x)
    x = layers.Dense(32, activation='relu')(x)
    
    output = layers.Dense(1, activation='sigmoid', name="win_prob")(x)

    model = models.Model(
        inputs=[blue_picks_in, red_picks_in, blue_bans_in, red_bans_in, stats_in],
        outputs=output
    )
    
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=0.001), loss='binary_crossentropy', metrics=['accuracy'])
    return model
