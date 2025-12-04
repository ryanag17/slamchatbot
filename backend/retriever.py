import json
from models import LocalModel

class SlamChatBot:
    def __init__(self):
        # Load all JSON files
        self.data = {}
        for fname in ["slam_art.json", "artists.json", "exhibitions.json", "other_data.json"]:
            with open(f"slam_data/{fname}", "r", encoding="utf-8") as f:
                self.data[fname] = json.load(f)

        # Initialize local model (Ollama)
        self.model = LocalModel("llama2")  # Example

    def get_answer(self, query: str) -> str:
        # Here you can implement retrieval + generation logic
        # Example: naive matching for demonstration
        for art in self.data["slam_art.json"]:
            if art.get("Title", "").lower() in query.lower():
                return art.get("Artist", "Unknown")
        # fallback: use model to answer based on data
        return self.model.generate(query, self.data)
