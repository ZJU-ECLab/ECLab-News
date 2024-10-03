# ECLab东西情报Beamer模板

## 生成pdf

### 使用GitHub Actions生成

fork这个仓库到自己的账号

删除`files`文件夹中的所有文件，并将所有收集的toml文件上传至`files`

修改`generate-tex.py`中的主编信息：

```python
editor_in_chief = ["Editor1, Degree", "Editor2, Degree"]
```

确保在仓库设置中允许运行actions

创建一个新的release并发布，等待actions完成即可在release中下载生成的pdf文件

### 本地生成

确保安装了所有依赖：`python, pip, virtualenv, texlive-full, make`

其中`texlive-full`不是硬性要求，但至少需要`xelatex`和一些宏包：
`beamer, ctex, newtxtext, fontenc, graphicx, hyperref`

首先克隆仓库到本地：

```bash
git clone https://gitee.com/edenqwq/eclab-beamer
cd eclab-beamer
```

进入`eclab-beamer`后，首先运行`make setup`构建python虚拟环境

然后运行`make`即可生成`tex/eclab-beamer.pdf`
