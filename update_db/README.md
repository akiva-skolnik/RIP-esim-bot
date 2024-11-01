# RIP-esim Data Collector

This project collects and processes data from the browser game [e-sim](https://alpha.e-sim.org), specifically for
the [RIP-esim](https://github.com/akiva-skolnik/RIP-esim-bot) Discord bot.

It gathers information about buffed players, player online time, and market price history.

## Key Features:

* **Automatic Data Collection:** Regularly fetches data from e-sim API & HTML pages.
* **Database:** Stores the collected data for efficient access and analysis.
* **Google Sheets Integration:** Makes specific data points readily available to users through Google Sheets.
* **Supports RIP-esim Bot:** Provides essential data for various bot functionalities.

**Benefits for e-sim Players:**

* **Track Market Trends:** Analyze historical market data to make informed investment decisions.
* **Monitor Player Activity:** Gain insights into player online time and buffing activity.
* **Stay Informed:** Access valuable data directly within the Discord bot.

## Running the Bot:
```bash
python3.12 -m update_db.bot
```

## Getting Involved:

* View Google Sheets Data:
    * [Market Price History](https://docs.google.com/spreadsheets/d/17y8qEU4aHQRTXKdnlM278z3SDzY16bmxMwrZ0RKWcEI)
    * [Player Online and Buff Time](https://docs.google.com/spreadsheets/d/1KqxbZ9LqS191wRf1VGLNl-aw6UId9kmUE0k7NfKQdI4#gid=1812695346)

## Support the Project:

The development and maintenance of this bot are ongoing. If you find it valuable, please consider supporting it through
a donation:

- [Buy Me a Coffee](https://www.buymeacoffee.com/ripEsim)
- [Patreon](https://www.patreon.com/ripEsim)

Your contributions will help ensure the bot's continued improvement and availability for the e-sim community.

### Thank you for your interest!
