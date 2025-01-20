from dotenv import load_dotenv
import base64
from flask_caching import Cache
import os
from flask import Flask
from PIL import Image
from io import BytesIO
import owncloud
import cv2
import numpy as np
from openai import OpenAI

app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'filesystem', 'CACHE_DIR': './tmp'})
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
NEXTCLOUD_URL = os.getenv("NEXTCLOUD_URL")
USERNAME = os.getenv("NEXTCLOUD_USERNAME")
PASSWORD = os.getenv("NEXTCLOUD_PASSWORD")
oc = owncloud.Client(NEXTCLOUD_URL)
oc.login(USERNAME, PASSWORD)


def get_newest_picture():
    """List files in the Nextcloud folder."""
    try:
        files = oc.list("water-measurements")
        if not files:
            print("No files found in the folder.")
            return None
        else:
            # return last image
            file = files[-1]
            print(f"Downloading file: {file.path}")

            image = BytesIO(oc.get_file_contents(file.path))

            return image

    except Exception as e:
        print(f"Error listing files: {e}")
        return None


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def OCR(image_url):
    image = encode_image(image_url)
    last_water = cache.get('water')
    last_water_string = f" The last value was: {last_water}. The current value should not be lower nor a lot higher." if last_water else "The value should be inbetween 00100000 and 00200000."
    print(last_water_string)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text",
                        "text": f"This is a close up image of a water meter. {last_water} Please give me the 8 digits (two starting 00). Only respond with numbers."},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image}"},
                    },
                ],
            }
        ],
    )
    return response.choices[0].message.content


def extract_text_from_image(image_bytes):
    """Apply OCR to an image to extract text."""
    try:
        # Load image from bytes
        image = Image.open(image_bytes).convert("L")
        # image = image.resize((image.width * 4, image.height * 4))
        image = np.array(image)
        image = cv2.rotate(image, cv2.ROTATE_180)

        image = image[490:560, 590:920]

        image_file = './output.jpg'
        cv2.imwrite(image_file, image)

        value = OCR(image_file)

        if len(value) != 8:
            return None

        value = value[:5] + '.' + value[5:]

        return value
    except Exception as e:
        print(f"Error during OCR: {e}")
        return None


def main():

    image = get_newest_picture()

    if not image:
        print("Failed to download the latest file.")
        return

    # Apply OCR to the image
    print("Applying OCR...")
    text = extract_text_from_image(image)
    cache.set('water', text, timeout=3600*24)
    if text:
        print("Extracted Text:")
        print(text)
        return text
    else:
        print("No text extracted from the image.")
        return None


@app.route('/', methods=['GET'])
@cache.cached(timeout=3600)
def call_function():
    # Call your function and return its output as a response
    result = main()
    if result:
        return str(result), 200
    else:
        return "No text extracted from the image.", 404


# Run the webserver
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
