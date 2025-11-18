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

def make_id(text):
    return hashlib.sha256(text.encode()).hexdigest()[:16]

# --------------------------
# Database Class
# --------------------------

class MemoryChroma:
    def __init__(self):
        self.db = chromadb.PersistentClient()
        if "ai_memories" in [c.name for c in self.db.list_collections()]:
            self.memories = self.db.get_collection("ai_memories")
        else:
            self.memories = self.db.create_collection("ai_memories")

    def embed_text(self, text):
        response = ollama.embeddings(
            model="nomic-embed-text",
            prompt=text
        )
        return response["embedding"]

    def add_memory(self, content):
        vector = self.embed_text(content)
        current_date = datetime.now().isoformat()
        timestamp = time.time()
        id = make_id(content)
        metadata = {
            "date": current_date,
            "recency": timestamp
        }
        self.memories.add(
            documents=[content],
            embeddings=[vector],
            metadatas=[metadata],
            ids=[id]

        )

    def get_memories(self, message, memory_limit=5, threshold=0.75, weight_similarity=0.7, weight_recency=0.3):
        # embed query
        query_vec = self.embed_text(message)
        # query Chroma
        results = self.memories.query(
            query_embeddings=[query_vec],
            n_results=50
        )

        docs = results['documents'][0]
        distances = results['distances'][0]      # similarity scores
        metadatas = results['metadatas'][0]

        # compute combined score per memory
        combined_scores = []
        for doc, sim, meta in zip(docs, distances, metadatas):
            if sim < threshold:
                continue  # skip irrelevant memories

            # compute recency score (normalize 0-1)
            recency_score = meta.get('recency', 0) / time.time()
            combined_score = weight_similarity * sim + weight_recency * recency_score
            combined_scores.append((doc, combined_score, meta))

        # sort by combined score descending
        combined_scores.sort(key=lambda x: x[1], reverse=True)

        # limit to top N memories
        final_docs = [doc for doc, score, meta in combined_scores[:memory_limit]]

        return final_docs

#hello

# --------------------------
# Memory Variables
# --------------------------
memory = MemoryChroma()
short_memory = []  # short-term (conversation context)
active_long_memories = set()  # working set (long-term context)




def fetch_response(message):
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
# --------------------------
# memory saving
# --------------------------
def should_save_memory(text):
    prompt = f"""
    Should this conversation be stored as long-term memory? Only consider:
    - Facts about the user
    - Emotional significance
    - Preferences or personality updates

    Answer only 'Yes' or 'No'.
    Exchange: {text}
    """
    response = fetch_response(prompt)
    response = response.strip().lower()
    if response.startswith("y"):   # matches 'Yes'
        return True
    else:                           # anything else treated as No
        return False

# --------------------------
# Summary Generation
# --------------------------
def summarise(prompt):
    summary_message = f'Summarize the following text concisely in one sentence, capturing the main facts, decisions, or important details only: {prompt}'
    summary = fetch_response(summary_message)
    return summary
# --------------------------
# Memory Retrieval
# --------------------------
def get_relevant_memories(message):
    global active_long_memories
    summary_message = summarise(message)
    memories = memory.get_memories(summary_message)
    count = 0
    for m in memories:
        count += 1
        if m not in active_long_memories:
            active_long_memories.add(m)
    return count


# --------------------------
# Message Handling
# --------------------------
def send_message():
    current_msg = my_entry.get().strip()
    if not current_msg:
        return

    # --- Add long-term memories ---
    count = get_relevant_memories(current_msg)
    message = """
        You have a long-term memory database and are provided with the last prompts and responses (short term memory..
        Do not end responses with generic sign-offs such as "Have a nice day," "Take care," or similar phrases. 
        If any previous prompts are provided don't respond with an introdcution or greeting, just continue the conversation.
        You are designed to be a conversational AI so don't provide rambling or technical responses unless specifically requested.
        \nRelevant long-term memories:\n
    """
    
    for m in active_long_memories:
        message += f"- {m}\n"

    # --- Add the previous conversation ---
    message += "\nPrevious prompts and responses in this chat session:\n"
    for content in short_memory:
        message += f"\n {content}\n"

    # --- Add the current prompt ---
    message += "\nCurrent prompt:\n"
    message += current_msg

    # Display user message
    chat_area.config(state='normal')
    chat_area.insert(tk.END, f"You: {current_msg}\n")
    chat_area.config(state='disabled')
    my_entry.delete(0, 'end')

    short_memory.append(f"User: {current_msg}")

    response = fetch_response(message)

    chat_area.config(state='normal')
    last_exchange = f"User: {current_msg}\nBot: {response}"
    bool_message = should_save_memory(last_exchange)
    print(bool_message)
    if bool_message or count == 0:
        summary_last_exchange = summarise(last_exchange)
        memory.add_memory(summary_last_exchange)
    

    short_memory.append(f"Bot: {response}")
    chat_area.insert(tk.END, f"Bot: {response}\n")


    chat_area.config(state='disabled')
    chat_area.yview(tk.END)  # auto-scroll to bottom

    #print("Short-term memory:", short_memory)
    print("Active long-term memories:", active_long_memories)




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
# Here is the code to make it grow vertically when text overflows horizontally
# The width attribute of Entry widget can be set dynamically based on content. 
my_entry['width'] = 1 # Set a default value for initial display

def resize_textarea(event):
    my_entry['width'] = len(event.widget.get()) + 1 # +1 for padding
    
# Bind the event when there is any interaction with Entry widget, so that it can adjust its width dynamically 
my_entry.bind('<Key>', resize_textarea)

send_button = tk.Button(frame, text="Send", width=10, command=send_message)
send_button.grid(row=1, column=1, sticky='e', padx=5, pady=5)

root.mainloop()