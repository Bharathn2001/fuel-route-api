import pandas as pd


INPUT_FILE = "data/fuel-prices.csv"
OUTPUT_FILE = "data/geocoding-input.csv"


def main():
    df = pd.read_csv(INPUT_FILE)

    geocoding_df = pd.DataFrame({
        "id": df["OPIS Truckstop ID"],
        "address": df["Address"],
        "city": df["City"],
        "state": df["State"],
        "zip": "",
    })

    geocoding_df.to_csv(
        OUTPUT_FILE,
        index=False,
        header=False,
    )

    print(f"Created: {OUTPUT_FILE}")
    print(f"Records: {len(geocoding_df)}")


if __name__ == "__main__":
    main()