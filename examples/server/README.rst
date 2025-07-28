Audio, video and data channel server
====================================

This example illustrates establishing audio, video and a data channel with a
browser. It also performs some image processing on the video frames using
OpenCV.

Running
-------

First install the required packages:

.. code-block:: console

    $ pip install aiohttp aiortc opencv-python

When you start the example, it will create an HTTP server which you
can connect to from your browser:

.. code-block:: console

    $ python server.py

You can then browse to the following page with your browser:

http://127.0.0.1:8080


Once you click `Start` the browser will send the audio and video from its
webcam to the server.

The server will play a pre-recorded audio clip and send the received video back
to the browser, optionally applying a transform to it.

In parallel to media streams, the browser sends a 'ping' message over the data
channel, and the server replies with 'pong'.

Additional options
------------------

If you want to enable verbose logging, run:

.. code-block:: console

    $ python server.py -v

Credits
-------

The audio file "demo-instruct.wav" was borrowed from the Asterisk
project. It is licensed as Creative Commons Attribution-Share Alike 3.0:

https://wiki.asterisk.org/wiki/display/AST/Voice+Prompts+and+Music+on+Hold+License


Note by Ruizhi:

1. If you want to run the client locally in the browser, make sure to use ``http://localhost:8080`` or ``http://127.0.0.1:8080``, not ``0.0.0.0:8080``!

2. If you want to run the client on an external device (e.g., a phone), follow these steps:

   a. **Generate Certificate on MacBook:**

      * Open Terminal and navigate to the project folder.
      * Run: ``openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -sha256 -days 365 -nodes``

   b. **Start Secure Server on MacBook:**

      * In the same Terminal window, run:
      * ``python server.py --cert-file cert.pem --key-file key.pem``

   c. **Connect from Android Device:**

      * Ensure the Android device is connected to the MacBook's WiFi hotspot.
      * Open the web browser on the Android device.
      * Navigate to: ``https://<Your-MacBook-IP>:8080``, e.g., ``https://192.168.2.1:8080``
      * Note: You must use ``https://``.

   d. **Bypass Browser Security Warning:**

      * When the "Your connection is not private" warning appears, select "Advanced".
      * Choose to "Proceed to 192.168.2.1 (unsafe)".

   e. **Start the Call:**

      * The page should now load correctly.
      * Click the "Start" button and grant microphone/camera permissions when prompted by the phone.


server_single_way is the unidirectional flow built by Ramakrishna and Bhuvana, it calls client.js and index.html. 
In index.html, I hide the video and data channel buttons, left only the audio button. 

server_genai.py, client_genai.js, index_genai.html are the code built by Ruizhi, which you can ignore at this moment
