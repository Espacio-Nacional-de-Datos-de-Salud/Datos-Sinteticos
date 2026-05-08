# Amazon EC2

EC2 provides easily scalable and configurable virtual servers, called *instances*. Instances can run many different Linux distributions, but the most common is Amazon Linux, which is specifically adapted to the platform. Windows can also be ran, but it has a higher cost and is less useful. They have a variety of options for computing power (number of CPUs, RAM, GPUs, etc.) and the amount of storage is completely up to you. These are the same instances that are launched during Sagemaker Code Editor sessions. However, Sagemaker puts several restrictions on these instances to ensure they work with other sagemaker features, most of which we are not using. One example is that Docker volumes are not allowed, and instead bind mounts are mandated. Additionally, we have encountered many issues trying to run a basic Docker Compose. As a result, we have decided to test deploying on a standalone EC2 instance, which will provide a much closer model to the client`s GCloud server they will use.

**IMPORTANT**: EC2 instances will never automatically shutdown, unless you create a CloudWatch alarm (which requires IT to do it or extra permissions). As such, if you are not actively running an application is it advisable to shut down the instance to avoid extra charges.

## Our instance

Our instance is *FNMT-PT05-TestInstance*, which may be viewed by searching EC2 on AWS and navigating to the Instances tab. It is of type t3.xlarge, providing 4 CPU cores and 16 GB of RAM at a cost of 0.1824 USD per hour. By default, we do not have permission to create instances, so it was created for us by filling out a ServiceNow request for a new Buiness IT Server, specifying the users that would connect. The most important factor of an instance is the security settings. These are managed by assigning an instance to a *Security Group*. Our instance is assigned to the group "backend". This allows all outgoing connections to the wider internet, but blocks incoming connections to only the specified ports and IPs. Ex. Allow port 22 TCP (SSH) from IP range 10.150.0.0/16 (in CIDR notation). On the instance page, the private IP address can be viewed, ours is 10.70.22.84. No public IP address is defined since this is a backend server.

## Connecting to instance

After the successful creation by IT of the instance, we were notified that we had been assigned user accounts on the system, with usernames corresponding to our existing short form usernames and passwords sent individually by email. Additionally, a PuTTy private key was provided for access over SSH. Theoretically, the server should be accessable over SSH when connecting to the VPN. However, we have not been able to accomplish this. Instead, we have been connecting through SSM, either with the web terminal or the CLI. 

### Web terminal
Ensure that your instance is started. Click *Connect*. Select the *SSM Session Manager* tab and click Connect. You now have a console as user "ssm-user".
If you run
```bash
ls /home
```
you will be able to see all users on the machine. 
Running
```bash
su USER
```
and replacing "USER" with your short username will allow you to switch accounts. As is typical in the command line, the terminal will not show any response while you type your password, but it is being inputted.

## Tips for use
By default, your account created by IT will not have sudo access. However, the ssm-user you log into as does. Amazon Linux uses the yum package manager, so you may install any requires packages through there using sudo. We did encounter some issues when attempting to download the latest docker-compose release from github using wget/curl. It appears the connection was blocked by the backend security rules. This was bypassed in a roundabout way by uploading the file to s3 from my laptop. The EC2 instance has by default the role *Role-System-Manager*, which allows full access to s3 (upload and download). Therefore, files may be downloaded using 
```bash
aws s3 cp s3://path/to/file .
```

## Installation of Docker Compose

from ssm-user
```bash
sudo yum update
sudo yum install docker
```

By default, the package lists do not seem to include docker-compose. If it did, you could install it through yum as well (with name docker-compose-plugin). You may choose to update the package lists in order to accomplish this. You may install docker compose for all users on the system or only for your user. These directions are taken from the docker [docs](https://docs.docker.com/compose/install/linux/#install-the-plugin-manually). These instructions assume that you will install it for all users.

First create the directory. This requires sudo
```bash
sudo mkdir -p /usr/local/lib/docker/cli-plugins
```
Next download docker compose. You should replace v5.1.2 with the most recent release from the [Github](https://github.com/docker/compose/releases/). This command did **not** work on our instance due to the aforementioned restrictions on the network.
```bash
curl -SL https://github.com/docker/compose/releases/download/v5.1.2/docker-compose-linux-x86_64 -o ~/docker-compose
```
If this command does not work for you, one option is to download the file directly on your machine (using the previous link), upload it to AWS S3 through the website or CLI, then download it using 
```bash
aws s3 cp s3://path/to/docker-compose-linux-x86_64 ~/docker-compose
```

Next, you will move this file to the proper directory and ensure it has the correct permissions

```bash
sudo mv ~/docker-compose /usr/local/lib/docker/cli-plugins/docker-compose
sudo chown root:root /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod 755 /usr/local/lib/docker/cli-plugins/docker-compose
```

Docker compose should now be installed. You may have to exit and re log in to the terminal for it to work. Verify by switching to your user and running the command
```bash
docker compose version
```

### Downloading of MLflow image

This step should be used if an external image cannot be downloaded due to the company firewall blocking it. We have encountered this issue with downloading the MLflow image.

First, make sure you have access to a machine that can download the image. In my case, my work laptop allowed for the download, but it was blocked in EC2 instances. For others, the download was not allowed on their work machines. Therefore, you may need to use a personal computer.


Download the image on the machine with access. References to MLflow can be replaced with another image if necessary.

```bash
docker save -o mlflowv3_10_1.tar ghcr.io/mlflow/mlflow:v3.10.1
```


Then move this tar file to the machine without access. This may be done with s3 as previously explained. Alternatively, the MLflow image is already uploaded to our s3 at `s3://ntt-ba-datalake/sp/health/FNMT-PT5/mlflowv3_10_1.tar`.

Once you have the tar file on the target machine, simply load the file with
```bash
docker load -i mlflowv3_10_1.tar
```
Docker should now recognize that this image is already present, and should no longer attempt to download it from the internet.

[<-- Back to Main Index](../../README.md)