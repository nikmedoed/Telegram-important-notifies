# Telegram important notifies
 The service will check all new messages from the selected chats and forward important message to you.

# Deploy
1. Set up `.env` or system environment
2. Install `requirements.txt`
3. Run `main.py` and login to your account once
4. Run `show_chats.py` and get id for important chats
5. Fill chat ids and query phrases in `db.py`
6. Edit `dosc/tg_notifies.service` for your user and copy to systemd, enable and start

# How it Works
**Configuration**:
- Define the recipient for forwarded messages.
- Specify the chats to monitor.
- Specify queries to search within messages.

**Functionality**:
- Upon initialization, the bot will scan and process all unread messages in the selected chats.
- It continuously monitors and processes incoming messages.
- After processing, messages are marked as read.
- If a message matches a predefined query, the bot forwards it to the specified recipient with a notification of the match.

# ToDo
- [x] Processing unreaded messages
  - [x] Simultaneous sending of info message and forwarding (mutex)
- [x] Forward all photos
- [ ] Flexible query combinations for different chats (queries for a specific chat)
- [ ] Storing queries and target chats in database
- [ ] Web-GUI for chat selecting and queries settings
- [x] Caching messages for duplicates detecting (from different chats etc.)
- [ ] Resistance to the disappearance of the Internet
- [ ] Emprove search engine by Word2Vec
