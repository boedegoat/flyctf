# FlyCTF

This repository contains a template for deploying CTF challenges on Fly.io, which provides a global network of servers and a simple CLI for deploying all kinds of applications easily at low cost.

## Benefits

-   **Low Cost**: Fly.io autostop machines when not in use (by default after 5 mins of idle), so you only pay for running machines.
-   **Docker Based**: Everything is based on Docker, even the main machine (Docker in Docker).
-   **SSL**: Free SSL certificates for your challenges out of the box.
-   **Easy to Use**: Fly.io has a simple CLI and web interface, so you can deploy and manage your challenges with just a few commands.
-   **Free Allowance**: You don't need to pay if your usage is under $5 per month and you can start for free.

## Cons

-   **Cold Start**: The first request to your challenge may take a few seconds to start up, as the machine needs to be started. But subsequent requests will be much faster.

## Getting Started

1. Create a Fly.io account
1. Install the Fly.io CLI: https://fly.io/docs/getting-started/installing-flyctl/
1. Login to your Fly.io account with `fly auth login`
1. Clone this repository
1. Run `fly launch --no-deploy` to create a new Fly.io app
1. Run `fly volumes create data --size 10 --region sin` to create a new 10gb of persisted storage. This is used for persisting docker container data. You can change the size and region to your liking.
1. Run `fly deploy` to deploy

## Deploying a new challenge

1. Create a new directory for your challenge inside the `challenges` directory
1. Build your challenge with `Dockerfile` and `docker-compose.yml`
1. In `docker-compose.yml`, make sure to expose the correct ports for your challenge. For example, if your challenge listens on port 80, you should have:

    ```yaml
    services:
        app:
            build: .
            ports:
                - '80:80'
    ```

1. Create `challenge.yml` file with the following structure:

    ```yaml
    internal_port: 80 # The port your challenge listens on
    public_port: 5000 # The port your challenge is exposed on
    ```

1. Edit `fly.toml`, add these to open your challenge port to public:

    ```toml
    [[services]]
    http_checks = []
    tcp_checks = []
    script_checks = []
    protocol = 'tcp'
    internal_port = 5000 # based on public_port in challenge.yml
    auto_stop_machines = 'stop' # stop machines after 5 mins of idle
    auto_start_machines = true
    min_machines_running = 0

    [[services.ports]]
    port = 5000 # based on public_port in challenge.yml
    handlers = ['tls', 'http']
    ```

1. Deploy your challenge with `fly deploy`
1. You can always refer to the current `challenges` directory for examples of how to build your own challenges

## Monitoring

1. Run `fly logs` to view the logs of your app
1. Run `fly ssh console` to access the console of your app
