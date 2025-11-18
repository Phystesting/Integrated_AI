from tkinter import *
import threading

class ChatBox:
    def __init__(self):
        self.root = Tk()
        self.text_widget = Text(self.root)
        self.text_widget.pack()

        # Create a frame for the text input field and a send button
        self.input_frame = Frame(self.root)
        self.input_field = Entry(self.input_frame)
        self.senlf.input_frame, text="Send", command=self.send)
        
        # Add the input field and send button to the frame
        self.input_field.pack(side=LEFT)
        self.send_button.pack(side=RIGHT)
        self.input_frame.pack()

    def send(self):
        msg = self.input_field.get()
        # Clear the input field
        self.input_field.delete(0, END)
        
        if msg == "kahby lame mechanism":
            response = "Kahby lame mechanism"
        else:
            response = ""
            
        # Insert a new line into the text widget and scroll to show it
        self.text_widget.insert(END, f"You: {msg}\nBot: {response}\n\n")
        self.text_widget.see(END)

    def start(self):
        # Start the tkinter event loop
        self.root.mainloop()

# Create a chat box and start it
chat = ChatBox()
chat.start()