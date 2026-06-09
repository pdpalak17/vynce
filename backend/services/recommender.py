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

def recommend_tracks(history_tracks: list, liked_tracks: list, disliked_ids: set, candidate_tracks: list, co_play_weights: dict = None, limit: int = 12) -> list:
    """
    Train a ListeningPatternMLP neural network on user's preference history
    and use it to rank and filter candidate tracks, applying seed and co-play boosts
    and adding dynamic recommendation reasons.
    """
    if not candidate_tracks:
        return []

    co_play_weights = co_play_weights or {}

    # Extract seed features for labeling reasons
    liked_artists = {t.get("artist") or t.get("track_artist") for t in liked_tracks if (t.get("artist") or t.get("track_artist"))}
    recent_artists = {t.get("artist") or t.get("track_artist") for t in history_tracks[:10] if (t.get("artist") or t.get("track_artist"))}
    recent_titles = {t.get("title") or t.get("track_title") for t in history_tracks[:10] if (t.get("title") or t.get("track_title"))}

    liked_artists = {a.lower().strip() for a in liked_artists if a}
    recent_artists = {a.lower().strip() for a in recent_artists if a}
    recent_titles = {t.lower().strip() for t in recent_titles if t}

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

    # If the user has no history or very little history, return a fallback list with generic reasons
    if len(positive_samples) < 2:
        candidates = [dict(c) for c in candidate_tracks if (c.get("id") or c.get("track_id")) not in disliked_ids]
        random.shuffle(candidates)
        res = []
        for c in candidates[:limit]:
            c["recommendation_reason"] = "Trending choice"
            res.append(c)
        return res

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
        track_dict = dict(track)
        tid = track_dict.get("id") or track_dict.get("track_id")
        if tid in disliked_ids:
            continue
            
        title = track_dict.get("title") or track_dict.get("track_title", "")
        artist = track_dict.get("artist") or track_dict.get("track_artist", "")
        
        x = extract_track_features(title, artist)
        pred, _, _ = nn.forward(x)
        
        # Base neural net preference score
        score = pred

        # Dynamic Reason Assignment and Boosts
        reason = "Recommended for you"
        artist_clean = artist.lower().strip()
        
        # 1. Co-play boost
        if tid in co_play_weights:
            score += 0.25 * co_play_weights[tid]
            reason = "Often played next"

        # 2. Liked Artist boost
        elif artist_clean in liked_artists:
            score += 0.15
            # Find the original capitalization of the artist name
            original_artist = artist
            for lt in liked_tracks:
                a_name = lt.get("artist") or lt.get("track_artist")
                if a_name and a_name.lower().strip() == artist_clean:
                    original_artist = a_name
                    break
            reason = f"Because you like {original_artist}"

        # 3. Recently played Artist boost
        elif artist_clean in recent_artists:
            score += 0.10
            original_artist = artist
            for ht in history_tracks:
                a_name = ht.get("artist") or ht.get("track_artist")
                if a_name and a_name.lower().strip() == artist_clean:
                    original_artist = a_name
                    break
            reason = f"Based on recent listens to {original_artist}"

        # 4. Genre similarity boost (based on Title features)
        elif "romantic" in title.lower() and "romantic" in "".join(recent_titles):
            score += 0.05
            reason = "Romantic vibe you like"
        elif "sad" in title.lower() and "sad" in "".join(recent_titles):
            score += 0.05
            reason = "Sad melodies you like"
        elif "party" in title.lower() and "party" in "".join(recent_titles):
            score += 0.05
            reason = "Party anthems you like"

        # Add slight noise (exploration vs exploitation) to prevent rigid repeats
        score += random.uniform(-0.03, 0.03)
        
        track_dict["recommendation_reason"] = reason
        scored_candidates.append((score, track_dict))

    # Sort candidates by final score descending
    scored_candidates.sort(key=lambda item: item[0], reverse=True)
    
    # Return top ranked tracks
    return [track for _, track in scored_candidates[:limit]]

