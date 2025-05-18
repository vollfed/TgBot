Bot is ready to summarize Youtube video, url or pdf files
It will consider last message as its context

## 🤖 Available Commands

- `/start` – Start the bot  
- `/help` – Show this help message  
- `/sl <lang_code>` – Set your preferred transcript language  
  _Example:_ `/sl en`  
- `/ts` – Fetch and save transcript from the most recent YouTube link you sent  
- `/gt` – Show the last saved title  
- `/gc` – Show the last saved context  
- `/sm` – Summarize the last saved transcript  
- `/ssm [max_len] [lang]` – Super summarize with optional max length and response language  
  _Example:_ `/ssm 300 ru`  
- `/select_model <gpt-4|local>` – Switch between GPT or local model  
- `/q <question>` – Ask a general question (no video context)  
- `/qc <question>` – Ask a question using saved context  
- `/cc <y|n>` –  Enable or disable *context continuation* (e.g. `/cc y`)

