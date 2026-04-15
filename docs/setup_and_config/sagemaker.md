[<-- Back to Main Index](../../README.md)

# AWS SageMaker Guide - Business Analytics

Guide to create your SageMaker profile, work from local VS Code through SSH, and control costs.

## 0. Prerequisite: Access to BA AWS

This guide assumes you already have access to the Business Analytics AWS environment. If you do not, start here:
- [AWS BA - Access 2025](https://everisgroup.sharepoint.com/:w:/s/businessanalytics/IQDlt6bmwINGRJe6HMorB8VnAcAKIzy_0D2Ev5ypY3T8fAs?e=GQsAoJ)

## 1. Access the SageMaker Environment

1. Open the **AWS Access Portal**: <https://awsitnegociobilling.awsapps.com/start/#/?tab=accounts>
2. Expand the **Proyecto_ProcessMining** account.
3. Click **DefaultProjectAccess**.
4. In the AWS console, search for **Amazon SageMaker AI**.
5. Confirm the region (top-right) is **eu-west-1 (Ireland)**.

## 2. Create Your User Profile

Within SageMaker AI, navigate to: **Environment configurations (left menu) -> Domains -> QuickSetupDomain-20240604T131727 -> User profiles -> Add user**.

**Profile name format**:
```text
{ntt_short_user}-{short_project_name}
```

**Mandatory tags** (for cost tracking):

| Tag | Value |
|-----|-------|
| `Team` | Health, Industry, Banking, etc. |
| `Project` | Same name used in your profile |
| `User` | Your NTT short user |

**Recommended settings:**
- Enable **MLflow** and **Docker**.
- Set **Idle time** as low as possible. This helps auto-stop instances when forgotten.

After creating the profile, it appears in the User Profiles list. Open it using **Open Studio** (Actions column).

## 3. Code Editor: Create Your Workspace

Inside Studio you can access **MLflow, RStudio, Jupyter, and Code Editor**.

1. Open **Code Editor** and click *Create new Code Editor space* (top-right).
2. Set name and configuration (see instance/storage guidance below).
3. Enable **Remote access** (required to connect from local VS Code via SSH).
    - Not all instance types are compatible with remote access.
    - The instance type can be changed each time the space is reactivated.
4. Click **Activate space**.

Once active, you have two options:
- **Open Code Editor**: opens SageMaker VS Code in the browser.
- **Open in VS Code**: opens local desktop VS Code connected through SSH. You may be asked to trust the source and install the SSH extension.

### Instance Types

Instance cost is charged while the instance is running, regardless of CPU utilization.

| Series | Behavior | When to use |
|-------|----------|-------------|
| `ml.m*` | Sustained full performance as needed. | Sustained or intensive workloads. |
| `ml.t*` | Lower cost, credit-based burst performance. If credits run out, performance decreases. | Light usage, testing, or development. |

### Storage

- Mounted at `/home`.
- **Always billed**, even when the space is stopped.
- Avoid oversized spaces or multiple unused spaces.

## 4. Clone a GitLab Repository

For complete GitLab connection and authentication instructions (including PAT creation and credential persistence), see:
- [GitLab Access and Usage Guide](gitlab.md)

## 5. Inactivity and Space Shutdown

Important cost notes:

- Closing local VS Code or losing SSH connection does **not** stop the SageMaker instance. The space continues running until configured idle time is reached.
- To stop compute billing immediately, **stop the space manually** in SageMaker.

Unsaved changes are not usually at risk. In browser Code Editor, changes are synced automatically within seconds, but opening the browser editor is not required for the selected instance compute billing to apply.

If the space is stopped, local VS Code access will stop working until you reactivate it.

## 6. Storage Management

### Check disk space

```bash
df -h
```

Typical output:
```text
Filesystem      Size  Used Avail Use% Mounted on
overlay          37G  144K   37G   1% /
tmpfs            64M     0   64M   0% /dev
/dev/nvme0n1p1  180G   88G   93G  49% /opt/.sagemakerinternal
/dev/nvme1n1     20G   15G  5.2G  75% /home/sagemaker-user
```

Focus on `/home/sagemaker-user`, where your files are stored. If it fills up, the environment may fail.

### Download data from S3

Example (Synthea synthetic data):

```bash
aws s3 cp --no-sign-request --recursive s3://synthea-omop/synthea1k/ ./synthea1k/
```

[<-- Back to Main Index](../../README.md)
