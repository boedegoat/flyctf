# FlyCTF

This repository contains a template for deploying CTF challenges on Fly.io, which provides a global network of servers and a simple CLI for deploying all kinds of applications easily at low cost.

## Benefits

- **Low Cost**: Fly.io autostop machines when not in use (by default after 5 mins of idle), so you only pay for what you use.
- **Docker Based**: Everything is based on Docker, even the main VM.
- **SSL**: Fly.io provides free SSL certificates for your challenges.
- **Easy to Use**: Fly.io has a simple CLI and web interface, so you can deploy your challenges with just a few commands.
- **Free Allowance**: You get $5 of free allowance every month and you can start for free.

## Getting Started

1. Install the Fly.io CLI: https://fly.io/docs/getting-started/installing-flyctl/
1. Create a Fly.io account
1. Clone this repository
1. Run `fly launch --no-deploy` to create a new Fly.io app
1. Run `fly volumes create data --region sin` to create a new volume
1. Run `fly deploy` to deploy

## Deploying a new challenge
1. Create a new directory for your challenge inside the `challenges` directory
1. Build your challenge with `Dockerfile` and `docker-compose.yml`
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
    internal_port = 5000 # Open port to public
    auto_stop_machines = 'stop'
    auto_start_machines = true
    min_machines_running = 0

    [[services.ports]]
    port = 5000 # Open port to public
    handlers = ['tls', 'http']
    ```
1. You can always refer to the current `challenges` directory for examples of how to build your own challenges

## Monitoring
1. Run `fly logs` to view the logs of your app
1. Run `fly ssh console` to access the console of your app
