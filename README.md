# eCFR Analyzer Backend

Python backend retrieving data from the ECFR API, performing analysis including word count, and supplying this to the frontend via ReST API.

## Usage

### Getting started

To run the eCFR Analyzer along with the API use the Docker compose file as follows:

```shell
 docker compose up --wait
 ```

And then navigate to [http://localhost:3000](http://localhost:3000) in your browser.

You should see something that looks like

![this](https://i.ibb.co/YB9MP8Jj/ecfr-frontend-pic.png)

go here if the above image is not working: https://i.ibb.co/YB9MP8Jj/ecfr-frontend-pic.png



#### Stopping the app

To stop the app, run:

```shell
docker compose down
```

## Running the app locally

```bash
# Create a virtual environment
uv lock
 
# Run the app. This will install dependencies with "uv"
uv run main.py
```

