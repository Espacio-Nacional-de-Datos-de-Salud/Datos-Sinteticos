[<-- Back to AWS SageMaker](sagemaker.md)

# GitLab Access and Usage Guide

Centralized guide for cloning repositories and configuring authentication with GitLab from local environments (Linux, macOS, WSL) and AWS SageMaker Code Editor.

## 1. Clone a Repository

Use the repository HTTP URL and clone it from your terminal:

```bash
git clone <gitlab-repo-http-url>
cd <repository-folder>
```

You can also clone from VS Code using **Command Palette -> Git: Clone** and pasting the same HTTP URL.

## 2. Authenticate with Personal Access Token (PAT)

For GitLab HTTPS authentication, use:
- **Username**: your GitLab username (as shown in your profile)
- **Password**: a **Personal Access Token (PAT)**

Normal account passwords may fail depending on your GitLab policy.

### Create a PAT

In GitLab:
1. Go to **Preferences -> Access Tokens**.
2. Click **Add new token**.
3. Define name, expiration, and required scopes.
4. Copy and store the token securely (you can reuse it until expiration).

## 3. Avoid Re-entering Credentials on Every Push/Pull

Run once in your environment (SageMaker terminal, local terminal, or WSL):

```bash
git config --global user.email "you@example.com"
git config --global user.name  "Your Name"
git config --global credential.helper store
```

On the next git operation, Git will ask for credentials once and persist them for future operations.

## 4. Environment Notes

- **WSL**: run all git commands inside your WSL terminal.
- **SageMaker Code Editor**: the same PAT-based flow applies when cloning from the editor or terminal.
- **Local VS Code**: if connected via SSH to SageMaker, credentials are stored in that remote environment.

[<-- Back to AWS SageMaker](sagemaker.md)