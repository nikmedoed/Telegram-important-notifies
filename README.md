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

# ToDo
- [x] Processing unreaded messages
  - [ ] Simultaneous sending of info message and forwarding (mutex)
- [ ] Resistance to the disappearance of the Internet
- [x] Forward all photos
- [ ] Storing queries and target chats in database
- [ ] Web-GUI for chat selecting and queries settings
- [ ] Flexible query combinations for different chats (queries for a specific chat)
- [ ] Caching messages for duplicates detecting (from different chats etc.)