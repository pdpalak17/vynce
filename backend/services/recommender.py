"""
Vynce Neural Network Recommender System
Lightweight pure-Python Multi-Layer Perceptron (MLP) for dynamic music recommendations
based on user listening history.
"""

import math
import random
import re

class ListeningPatternMLP:
    """
    A lightweight, pure-Python Multi-Layer Perceptron (MLP) neural network.
    It learns a user's music preference patterns from their listening history
    and predicts preference scores for candidate tracks.
    """
    def __init__(self, input_dim=64, hidden_dim=32):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        
        # Initialize weights (Xavier/He initialization)
        val1 = math.sqrt(2.0 / input_dim)
        self.w1 = [[random.uniform(-val1, val1) for _ in range(hidden_dim)] for _ in range(input_dim)]
        self.b1 = [0.0] * hidden_dim
        
        val2 = math.sqrt(2.0 / hidden_dim)
        self.w2 = [random.uniform(-val2, val2) for _ in range(hidden_dim)]
        self.b2 = 0.0

    def relu(self, x):
        return max(0.0, x)

    def relu_derivative(self, x):
        return 1.0 if x > 0.0 else 0.0

    def sigmoid(self, x):
        x = max(-500.0, min(500.0, x))
        return 1.0 / (1.0 + math.exp(-x))

    def forward(self, x):
        # Hidden layer: z1 = x * w1 + b1, a1 = relu(z1)
        z1 = [0.0] * self.hidden_dim
        for j in range(self.hidden_dim):
            val = sum(x[i] * self.w1[i][j] for i in range(self.input_dim))
            z1[j] = val + self.b1[j]
        
        a1 = [self.relu(val) for val in z1]
        
        # Output layer: z2 = a1 * w2 + b2, a2 = sigmoid(z2)
        z2 = sum(a1[j] * self.w2[j] for j in range(self.hidden_dim)) + self.b2
        a2 = self.sigmoid(z2)
        
        return a2, z1, a1

    def train_step(self, x, y, lr=0.05):
        # Forward pass
        pred, z1, a1 = self.forward(x)
        
        # Binary cross entropy loss gradient w.r.t z2: (pred - y)
        d_z2 = pred - y
        
        # Gradients for w2, b2
        d_w2 = [d_z2 * a1[j] for j in range(self.hidden_dim)]
        d_b2 = d_z2
        
        # Gradients backpropagated to hidden layer
        d_a1 = [d_z2 * self.w2[j] for j in range(self.hidden_dim)]
        d_z1 = [d_a1[j] * self.relu_derivative(z1[j]) for j in range(self.hidden_dim)]
        
        # Gradients for w1, b1
        d_w1 = [[0.0] * self.hidden_dim for _ in range(self.input_dim)]
        for i in range(self.input_dim):
            for j in range(self.hidden_dim):
                d_w1[i][j] = d_z1[j] * x[i]
        d_b1 = d_z1
        
        # Update weights & biases
        for i in range(self.input_dim):
            for j in range(self.hidden_dim):
                self.w1[i][j] -= lr * d_w1[i][j]
        for j in range(self.hidden_dim):
            self.b1[j] -= lr * d_b1[j]
            self.w2[j] -= lr * d_w2[j]
        self.b2 -= lr * d_b2

def extract_track_features(title: str, artist: str) -> list:
    """
    Map track title & artist metadata into a normalized 64-dimensional feature vector.
    """
    vector = [0.0] * 64
    text = f"{title} {artist}".lower()
    words = re.findall(r'[a-z0-9]+', text)
    
    # Hashing trick for text features (dims 0-47)
    for word in words:
        hash_val = sum(ord(c) * (31 ** idx) for idx, c in enumerate(word[:10]))
        idx = hash_val % 48
        vector[idx] += 1.0
        
    # L2 Normalization of the text section
    norm = math.sqrt(sum(v * v for v in vector[:48]))
    if norm > 0:
        for idx in range(48):
            vector[idx] /= norm
            
    # Domain-specific sentiment & genre markers (dims 48-63)
    if any(w in text for w in ["love", "romantic", "pyar", "dil", "ishq", "tum", "sanam", "romance"]):
        vector[48] = 1.0
    if any(w in text for w in ["sad", "judai", "dard", "tujhe", "rona", "cry", "broken", "tanha"]):
        vector[49] = 1.0
    if any(w in text for w in ["party", "dance", "club", "dj", "nach", "remix", "beat", "shake"]):
        vector[50] = 1.0
    if any(w in text for w in ["90s", "classic", "old", "retro", "kishore", "lata", "rafi", "rdburman"]):
        vector[51] = 1.0
    if any(w in text for w in ["punjabi", "singh", "dhillon", "sidhu", "jassi", "diljit"]):
        vector[52] = 1.0
    if "arijit" in text:
        vector[53] = 1.0
    if "rahman" in text:
        vector[54] = 1.0
    if "lofi" in text or "lo-fi" in text:
        vector[55] = 1.0
        
    return vector

def recommend_tracks(history_tracks: list, liked_tracks: list, disliked_ids: set, candidate_tracks: list, limit: int = 12) -> list:
    """
    Train a ListeningPatternMLP neural network on user's preference history
    and use it to rank and filter candidate tracks.
    """
    if not candidate_tracks:
        return []
        
    # Build positive training samples (history and liked songs)
    positive_samples = []
    seen_pos_ids = set()
    
    for t in liked_tracks:
        tid = t.get("id") or t.get("track_id")
        if tid and tid not in seen_pos_ids and tid not in disliked_ids:
            seen_pos_ids.add(tid)
            title = t.get("title") or t.get("track_title", "")
            artist = t.get("artist") or t.get("track_artist", "")
            positive_samples.append((title, artist))
            
    for t in history_tracks:
        tid = t.get("id") or t.get("track_id")
        if tid and tid not in seen_pos_ids and tid not in disliked_ids:
            seen_pos_ids.add(tid)
            title = t.get("title") or t.get("track_title", "")
            artist = t.get("artist") or t.get("track_artist", "")
            positive_samples.append((title, artist))

    # If the user has no history or very little history, return a fallback diverse list
    if len(positive_samples) < 2:
        candidates = [c for c in candidate_tracks if (c.get("id") or c.get("track_id")) not in disliked_ids]
        random.shuffle(candidates)
        return candidates[:limit]

    # Build negative training samples from candidates not listened to/liked
    negative_samples = []
    for c in candidate_tracks:
        cid = c.get("id") or c.get("track_id")
        if cid and cid not in seen_pos_ids:
            title = c.get("title") or c.get("track_title", "")
            artist = c.get("artist") or c.get("track_artist", "")
            negative_samples.append((title, artist))
            if len(negative_samples) >= len(positive_samples) * 2:
                break
                
    # Fallback if no negatives could be gathered
    if not negative_samples:
        negative_samples = [("heavy metal noise", "unknown"), ("experimental synth test", "test")]

    # Assemble training data
    train_data = []
    for title, artist in positive_samples:
        train_data.append((extract_track_features(title, artist), 1.0))
    for title, artist in negative_samples:
        train_data.append((extract_track_features(title, artist), 0.0))

    # Initialize neural network
    nn = ListeningPatternMLP(input_dim=64, hidden_dim=32)
    
    # Train the MLP model for 15 epochs
    for _ in range(15):
        random.shuffle(train_data)
        for x, y in train_data:
            nn.train_step(x, y, lr=0.05)

    # Score all candidate tracks
    scored_candidates = []
    for track in candidate_tracks:
        tid = track.get("id") or track.get("track_id")
        if tid in disliked_ids:
            continue
            
        title = track.get("title") or track.get("track_title", "")
        artist = track.get("artist") or track.get("track_artist", "")
        
        x = extract_track_features(title, artist)
        pred, _, _ = nn.forward(x)
        
        # Add slight noise (exploration vs exploitation) to prevent rigid repeats
        score = pred + random.uniform(-0.05, 0.05)
        scored_candidates.append((score, track))

    # Sort candidates by neural network score descending
    scored_candidates.sort(key=lambda item: item[0], reverse=True)
    
    # Return top ranked tracks
    return [track for _, track in scored_candidates[:limit]]
