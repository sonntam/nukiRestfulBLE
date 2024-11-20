# Nuki BLE REST API Server

This is a Python-based REST API server service that allows pairing with and controlling Nuki door locks via Bluetooth Low Energy (BLE). The server is built using the `pyNukiBT` package for Nuki BLE communication, `Flask` for the web server framework, and `Flasgger` for generating the API documentation.

## Table of Contents
- [Installation](#installation)
- [Usage](#usage)
- [API Documentation](#api-documentation)
- [Docker](#docker)
- [Contributing](#contributing)
- [License](#license)

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/sonntam/nukiRestfulBLE.git
   cd nukiRestfulBLE
   ```

2. **Create a virtual environment and activate it:**
   ```bash
   python -m venv venv
   source venv/bin/activate   # On Windows use `venv\Scripts\activate`
   ```

3. **Install the required packages:**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. **Start the server:**
   
   ```bash
   python restserver.py
   ```

2. **Access the REST API documentation:**
   
   Open your web browser and navigate to [http://localhost:51001/apidocs/](http://localhost:51001/apidocs/).

3. **Settings:**
   
   Upon first start a default settings JSON file `config.json` is generated in the folder `settings` of the current working directory. Here you may change the binding or port as well as view the generated keys for communication with Nuki devices.

## API Documentation

You can view the complete REST API documentation by accessing the following URL in your browser:
[http://<server>:51001/apidocs/](http://<server>:51001/apidocs/)

## Docker

A `Dockerfile` is provided that can run the service within a Docker container.

To build the Docker image, use the following command:
```bash
docker build --network=host -t nukiRestfulBLE .
```

As the docker container needs access to bluetooth devices you have to run it wit hthe `SYS_ADMIN` and `NET_ADMIN` capabilities. Also `/var/run/dbus` has to be mapped. You may run the container using the following command

```bash
docker rm -f nukiService 
docker run -d --rm --name nukiService \ 
    --cap-add=SYS_ADMIN \
    --cap-add=NET_ADMIN --net=host \
    -v ./settings:/app/settings \
    -v /var/run/dbus:/var/run/dbus nukiRestfulBLE
```

## Example usage using cURL

Suppose your Nuki device has got "54:D2:72:AA:AA:AA" as MAC address. You can find it e.g. using the `/scan` method.
Then the following calls can be made:

```bash
curl -X GET http://127.0.0.1:51001/scan
curl -X POST http://127.0.0.1:51001/pair -H "Content-Type: application/json" -d '{"address": "54:D2:72:AA:AA:AA"}'
curl -X GET http://127.0.0.1:51001/listPaired
curl -X GET http://127.0.0.1:51001/state?address=54:D2:72:AA:AA:AA
curl -X POST http://127.0.0.1:51001/lock -H "Content-Type: application/json" -d '{"address": "54:D2:72:AA:AA:AA"}'
curl -X POST http://127.0.0.1:51001/unlock -H "Content-Type: application/json" -d '{"address": "54:D2:72:AA:AA:AA"}'
curl -X POST http://127.0.0.1:51001/unlatch -H "Content-Type: application/json" -d '{"address": "54:D2:72:AA:AA:AA"}'
curl -X POST http://127.0.0.1:51001/unpair -H "Content-Type: application/json" -d '{"address": "54:D2:72:AA:AA:AA"}'
```


## Contributing

Contributions are welcome! Please follow these steps to contribute:

1. Fork the repository.
2. Create a new feature branch (`git checkout -b feature/YourFeature`).
3. Commit your changes (`git commit -m 'Add some feature'`).
4. Push to the branch (`git push origin feature/YourFeature`).
5. Open a pull request.

## Disclaimer

I cannot be held responsible for any security problems with this service. It was intended for private use in secured environments only. Also I'm not good at programming python - please beware!

This has been tested and found working on a Raspberry Pi5 with it's integrated bluetooth adapter.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
