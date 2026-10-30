# Snooker Manager (Python)

A desktop application for managing a snooker club, built with **Python** and **Tkinter**. It keeps track of customers, games played, money owed (khata), century games, and daily reports, all stored locally so it works without internet.

> Available as an Android app: [Snooker_Manager_flutter](https://github.com/mesamraza157-code/Snooker_Manager_flutter)
> Also available in Releases of My Github Account
## Features

- **Customer Khata (Ledger):** Keep a separate record for every visitor with games played, amount owed, and payments received.
- **Century Section:** Multiple players (4, 5 or more) play together. Each player's name is shown with their own score, and scores update live as points are added.
- **Time-Based Century Charges:** The hourly rate is set in Settings. The start time is saved when a century begins, and the charge is calculated automatically from the elapsed time when it is closed.
- **Game History:** View all past games and sessions.
- **Reports:** Daily and overall reports of earnings and pending balances.
- **Settings:** Configure rates and other options.
- **Offline & Local:** All data is stored in a local database on your PC.

## Requirements

- Python 3.8 or newer
- Tkinter (included with most Python installations)

On Linux, if Tkinter is missing:

```bash
sudo apt install python3-tk        # Ubuntu / Debian
sudo pacman -S tk                  # Arch / Manjaro
```

## Installation

```bash
git clone https://github.com/mesamraza157-code/Snooker_Manager_python.git
cd Snooker_Manager_python
pip install -r requirements.txt    # only if the file exists
```

## Usage

```bash
python snooker_manager.py
```

## How It Works

1. **Add a customer** and start recording their games in the khata.
2. **Start a century** by adding the players. Add scores for each player as the game goes on.
3. **Close the century.** The total time is calculated and the charge is added using the hourly rate from Settings.
4. **Record payments** against a customer's khata whenever they pay.
5. **Check reports** to see earnings and pending amounts.

## Project Structure

```
Snooker_Manager_python/
├── snooker_manager.py    # Main application
├── README.md
└── .gitignore
```

## Data & Privacy

The database file (`.db` / `.sqlite`) contains real customer and ledger data, so it is excluded from the repository via `.gitignore`. A fresh database is created automatically on first run.

## Roadmap

- [x] Khata, century scoreboard, reports
- [x] Flutter Android version
- [ ] Data backup / export
- [ ] Printable receipts

## Author

**Mesam Raza**
GitHub: [@mesamraza157-code](https://github.com/mesamraza157-code)

## License

This project is for personal and educational use. Add a license (for example MIT) if you want to allow others to use it.
