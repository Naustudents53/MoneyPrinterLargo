
## Installation

> ⚠️ If you are planning to reach out to scraped businesses per E-Mail, please first install the [Go Programming Language](https://golang.org/).

```bash
git clone https://github.com/FujiwaraChoki/MoneyPrinterPro.git

cd MoneyPrinterPro
# Copy Example Configuration and fill out values in config.json
cp config.example.json config.json

# Create a virtual environment
python -m venv venv

# Activate the virtual environment - Windows
.\venv\Scripts\activate

# Activate the virtual environment - Unix
source venv/bin/activate

# Install the requirements
pip install -r requirements.txt
```

## Usage

```bash
# Run the application
python src/main.py
```

## Documentation

All relevant document can be found [here](docs/).

## Scripts

For easier usage, there are some scripts in the `scripts` directory, that can be used to directly access the core functionality of MPP, without the need of user interaction.

All scripts need to be run from the root directory of the project, e.g. `bash scripts/upload_video.sh`.

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct, and the process for submitting pull requests to us. Check out [docs/Roadmap.md](docs/Roadmap.md) for a list of features that need to be implemented.

## Code of Conduct

Please read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for details on our code of conduct, and the process for submitting pull requests to us.

## License

MoneyPrinterPro is licensed under `Affero General Public License v3.0`. See [LICENSE](LICENSE) for more information.

## Acknowledgments

- [KittenTTS](https://github.com/KittenML/KittenTTS)
- [gpt4free](https://github.com/xtekky/gpt4free)

## Disclaimer

This project is for educational purposes only. The author will not be responsible for any misuse of the information provided. All the information on this website is published in good faith and for general information purpose only. The author does not make any warranties about the completeness, reliability, and accuracy of this information. Any action you take upon the information you find on this website (FujiwaraChoki/MoneyPrinterPro), is strictly at your own risk. The author will not be liable for any losses and/or damages in connection with the use of our website.
