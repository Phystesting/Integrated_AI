import tkinter as tk
from tkinter import scrolledtext
import requests
import json
import sqlite3
import re
import chromadb
import ollama
from datetime import datetime
import time
import hashlib
import numpy as np



# --------------------------
# Memory Class
# -------------------------- 
class MemoryChroma:
    def __init__(self, fetch_response_fn):
        self.db = chromadb.PersistentClient()
        if "ai_memories" in [c.name for c in self.db.list_collections()]:
            self.memories = self.db.get_collection("ai_memories")
        else:
            self.memories = self.db.create_collection("ai_memories",embedding_function=None,metadata={"hnsw:space": "cosine"})
        self.short_memory = []
        self.active_long_memories = set()
        self.fetch_response = fetch_response_fn
        print(self.memories._client.get_collection("ai_memories").metadata)
        
    def normalise_vec(self,v):
        vec = v / np.linalg.norm(v)
        return vec.tolist()
    
    def embed_text(self, text):
        response = ollama.embeddings(
            model="nomic-embed-text",
            prompt=text
        )
        return response["embedding"]

    def summarise(self, text):
        msg = (
            "Summarize the following text concisely in one sentence, "
            "capturing only the main facts, decisions or important details: "
            + text
        )
        return self.fetch_response(msg)
    
    def generate_tags(self, text):
        prompt = f"""
            Extract 3–6 high-level semantic tags that capture the core concepts.

            Output the tags as a JSON array of strings only, like:
            ["tag1", "tag2", "tag3"]

            If you add any other text, still ensure the array appears exactly once
            in that format so it can be extracted.

            Text: {text}
        """
        tag_string = self.fetch_response(prompt)
        tags = re.findall(r'"(.*?)"', tag_string)
        return tags
        
    def make_id(self,text):
        return hashlib.sha256(text.encode()).hexdigest()[:16]
    def add_memory(self, content):
        summary_content = self.summarise(content)
        tag_content = self.generate_tags(content)
        vector = np.array(self.embed_text(content))
        normalised_vec = self.normalise_vec(vector)
        current_date = datetime.now().isoformat()
        timestamp = time.time()
        id = self.make_id(content + f"{timestamp}")
        metadata = {"date": current_date, "recency": timestamp, "tags": json.dumps(tag_content)}
        self.memories.add(
            documents=[summary_content],
            embeddings=[normalised_vec],
            metadatas=[metadata],
            ids=[id]
        )
    def should_save_memory(self, text):
        prompt = f"""
        Should this conversation be stored as long-term memory? Only consider:
        - Facts about the user
        - Emotional significance
        - Preferences or personality updates

        Answer only 'Yes' or 'No'.
        Exchange: {text}
        """
        response = self.fetch_response(prompt)
        response = response.strip().lower()
        if response.startswith("y"):   # matches 'Yes'
            return True
        else:                           # anything else treated as No
            return False
    def get_memories(self, message, memory_limit=5, threshold=0.55, weight_similarity=1.0):
        query_vec = np.array(self.embed_text(message))
        tag_message = self.generate_tags(message)
        normalised_query_vec = self.normalise_vec(query_vec)

        results = self.memories.query(
            query_embeddings=[normalised_query_vec],
            n_results=50
        )

        docs = results['documents'][0]
        distances = results['distances'][0]
        metadatas = results['metadatas'][0]

        combined = []
        tag_memories = []

        for doc, dist, meta in zip(docs, distances, metadatas):

            # Convert distance -> similarity
            sim = 1 - dist  

            # Tags (safe default: [])
            tags = json.loads(meta.get("tags", []))

            # Tag overlap
            common_tags = set(tag_message) & set(tags)
            if common_tags:
                tag_memories.append(doc)

            # Skip memories below similarity threshold
            if sim < threshold:
                continue

            combined.append((doc, sim))

        # Sort by similarity
        combined.sort(key=lambda x: x[1], reverse=True)

        # Take top N semantic memories
        semantic_results = [doc for doc, score in combined[:memory_limit]]

        # Deduplicate while keeping order
        final = []
        seen = set()
        for doc in [*semantic_results, *tag_memories]:
            if doc not in seen:
                seen.add(doc)
                final.append(doc)

        return final


    def get_relevant_memories(self, message):
        memories = self.get_memories(message)

        count = 0
        for m in memories:
            if m not in self.active_long_memories:
                self.active_long_memories.add(m)
            count += 1

        return count


# --------------------------
# personality growth
# --------------------------
class Personality_module:
    def __init__(self, personality_file, fetch_response_fn):
        self.personality_file = personality_file
        self.fetch_response = fetch_response_fn

    def emotion_buffer(self, text):
        prompt = f"""
        Please state how this exchange would make the person labelled bot feel, including negative emotions if they are present.
        Describe in 3–4 sentences:
        - how bot emotionally feels about this exchange
        - why it feels that way (briefly)
        Do NOT output chain-of-thought or analysis steps. 
        Use natural language emotion labels.

        Exchange: {text}
        """
        response = self.fetch_response(prompt)
        response = response.strip().lower()
        return response

    def _load_personality(self):
        try:
            with open(self.personality_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_personality(self, existing_personality):
        with open(self.personality_file, "w") as f:
            json.dump(existing_personality, f, indent=4)
    
    def personality_traits_growth(self, emotions_string):
        prompt = f"""
        You are determining personality traits that would increase in strength 
        based on the following emotional reflection.

        Provide ONLY a JSON array of strings.
        1 to 5 traits max.
        Traits should be short (1–3 words each).
        Do not explain.

        Feelings: {emotions_string}

        Output example:
        ["trait1", "trait2"]
        """
        response = self.fetch_response(prompt).strip()
        existing_personality = self._load_personality()
        traits = re.findall(r'"(.*?)"', response)
        for trait in traits:
            if trait in existing_personality:
                existing_personality[trait] += 0.08
                if existing_personality[trait] > 1.0:
                    existing_personality[trait] = 1.0
            else:
                existing_personality[trait] = 0.2
        self._save_personality(existing_personality)
        
    def personality_traits_decay(self, emotions_string):
        prompt = f"""
        You are determining which personality traits would weaken or decrease in relevance
        based on the following emotional reflection.

        Provide ONLY a JSON array of strings.
        1 to 5 traits max.
        Traits should be short (1–3 words each).
        Do not explain.

        Feelings: {emotions_string}

        Output example:
        ["trait1", "trait2"]
        """
        response = self.fetch_response(prompt).strip()
        existing_personality = self._load_personality()
        traits = re.findall(r'"(.*?)"', response)
        for trait in traits:
            if trait in existing_personality:
                existing_personality[trait] -= 0.05
                if existing_personality[trait] <= 0.0:
                    existing_personality.pop(trait)
        self._save_personality(existing_personality)
            
    def update_personality(self, text):
        emotion_string = self.emotion_buffer(text)
        self.personality_traits_growth(emotion_string)
        self.personality_traits_decay(emotion_string)
    
    def generate_personality(self):
        current_personality = self._load_personality()
        personality_string = "Personality strength parameters:\n"
        for key, value in current_personality.items():
            if value > 0.8:
                personality_string += f"{key}: very strong\n"
            elif value > 0.5:
                personality_string += f"{key}: strong\n"
            elif value > 0.2:
                personality_string += f"{key}: medium\n"
            else:
                personality_string += f"{key}: weak\n"
        return personality_string

# --------------------------
# Chatbot Core
# --------------------------
class Chatbot:
    def __init__(self):
        self.memory = MemoryChroma(self.fetch_response)
        self.personality = Personality_module("personality_v1.json", self.fetch_response)
        self.short_memory = []

    def fetch_response(self, message):
        prompt = json.dumps({
            "model": "gpt-oss:20b",
            "prompt": message
        })

        response = requests.post(
            "http://localhost:11434/api/generate",
            headers={"Content-Type": "application/json"},
            data=prompt,
            stream=True
        )
        message_out = ""
        for line in response.iter_lines():
            try:
                obj = json.loads(line)
                if "response" in obj:
                    message_out += obj["response"]
            except:
                continue
        return message_out
        
    def send_message(self):
        current_msg = my_entry.get().strip()
        if not current_msg:
            return

        # --- Add long-term memories ---
        count = self.memory.get_relevant_memories(current_msg)

        message = """
        You are designed to be as human like as possible, to meet this end you have been given;
        A long-term memory database and are provided with the last prompts and responses (short term memory).
        Ontop of this as you create memories, these memories update your personality allowing you to grow as a person would.
        Your personality is displayed as a series of traits and strengths.
        Do not end responses with generic sign-offs. 
        Keep responses concise and human like and attempt to continue the conversation naturally.
        Do not produce numbered lists unless requested keep to a regular spoken format.
        """
        
        current_personality = self.personality.generate_personality()
        message += f"\n{current_personality}\n"
        
        message += "Relevant long-term memories:"
        for m in self.memory.active_long_memories:
            message += f"- {m}\n"

        message += "\nPrevious prompts and responses in this chat session:\n"
        for content in self.memory.short_memory:
            message += f"\n {content}\n"

        message += "\nCurrent prompt:\n"
        message += current_msg

        chat_area.config(state='normal')
        chat_area.insert(tk.END, f"You: {current_msg}\n")
        chat_area.config(state='disabled')
        my_entry.delete(0, 'end')

        self.memory.short_memory.append(f"User: {current_msg}")

        response = self.fetch_response(message)

        chat_area.config(state='normal')
        last_exchange = f"User: {current_msg}\nBot: {response}"
        bool_message = self.memory.should_save_memory(last_exchange)
        if bool_message or count == 0:
            self.personality.update_personality(last_exchange)
            self.memory.add_memory(last_exchange)

        self.memory.short_memory.append(f"Bot: {response}")
        chat_area.insert(tk.END, f"Bot: {response}\n")
        chat_area.config(state='disabled')
        chat_area.yview(tk.END)

        print("Active long-term memories:", self.memory.active_long_memories)


# --------------------------
# UI Setup
# --------------------------
root = tk.Tk()
root.title("AI Chatbot")
root.geometry("500x400")

frame = tk.Frame(root)
frame.pack(fill='both', expand=True, padx=10, pady=10)

frame.grid_rowconfigure(0, weight=1)
frame.grid_columnconfigure(0, weight=1)
frame.grid_columnconfigure(1, weight=0)

chat_area = scrolledtext.ScrolledText(frame, wrap='word', bg='#f2f2f2', state='disabled')
chat_area.grid(row=0, column=0, columnspan=2, sticky='nsew', padx=5, pady=5)

my_entry = tk.Entry(frame)
my_entry.grid(row=1, column=0, sticky='ew', padx=5, pady=5, ipady=5)
my_entry['width'] = 1

def resize_textarea(event):
    my_entry['width'] = len(event.widget.get()) + 1

my_entry.bind('<Key>', resize_textarea)

chatbot = Chatbot()

send_button = tk.Button(frame, text="Send", width=10, command=chatbot.send_message)
send_button.grid(row=1, column=1, sticky='e', padx=5, pady=5)

root.mainloop()
