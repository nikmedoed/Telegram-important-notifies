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


---

# 💖 Support my work

<table align="center" border="0" cellpadding="0" cellspacing="0">
  <tr>
    <td><a href="https://ko-fi.com/nikmedoed"><img src="https://img.shields.io/badge/Ko--fi-donate-FF5E5B?logo=kofi" alt="Ko-fi" border="0"></a></td>
    <td><a href="https://boosty.to/nikmedoed/donate"><img src="https://img.shields.io/badge/Boosty-donate-FB400B?logo=boosty" alt="Boosty" border="0"></a></td>
    <td><a href="https://paypal.me/etonikmedoed"><img src="https://img.shields.io/badge/PayPal-donate-00457C?logo=paypal" alt="PayPal" border="0"></a></td>
    <td><a href="https://yoomoney.ru/to/4100119049495394"><img src="https://img.shields.io/badge/YooMoney-donate-8b3ffd?logo=yoomoney" alt="YooMoney" border="0"></a></td>
    <td><a href="https://github.com/nikmedoed#-support-my-work"><img src="https://img.shields.io/badge/Other-more-lightgrey?logo=github" alt="Other" border="0"></a></td>
  </tr>
</table>
