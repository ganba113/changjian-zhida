# LibreOffice 离线安装说明（openEuler 22.03 aarch64）

用于解析 doc/wps 老格式文档（后端会自动优先调用 soffice 转换）。

## 一、上传并解压

把 `LibreOffice_26.2.6_Linux_aarch64_rpm.tar.gz` 上传到服务器（约 229MB），解压：

```bash
cd /opt
tar -xzf LibreOffice_26.2.6_Linux_aarch64_rpm.tar.gz
# 解压出 LibreOffice_26.2.6.3_Linux_aarch64_rpm/ 目录
```

## 二、安装（二选一）

### 方式 A：标准 rpm 安装（推荐，root）

```bash
cd /opt/LibreOffice_26.2.6.3_Linux_aarch64_rpm/RPMS
rpm -ivh --nodeps *.rpm
```

> `--nodeps` 跳过依赖检查直接安装。LibreOffice 运行时若缺系统库会报错，见「三、依赖处理」。

### 方式 B：官方用户模式安装（不需 root，装到指定目录）

```bash
cd /opt/LibreOffice_26.2.6.3_Linux_aarch64_rpm
./install ./RPMS /opt/libreoffice
```

## 三、依赖处理（关键）

LibreOffice 需要一些系统库，openEuler 22.03 基础版可能缺个别库。安装后先测试：

```bash
soffice --headless --version
# 或方式B：
/opt/libreoffice/program/soffice --headless --version
```

**如果报 `error while loading shared libraries: libXXX.so`**，说明缺库。把缺的库名（libXXX）发给我，我从 openEuler 22.03 源下载对应的 rpm 包再传给你。

常见可能缺失的库：`libX11`、`libXext`、`libcups`、`libcairo` 等（X11 图形库和打印库）。

## 四、确保 soffice 可被后端调用

后端通过 `soffice` 或 `libreoffice` 命令检测。安装后确认命令在 PATH 里：

```bash
which soffice
```

如果不在 PATH（方式 B 装到 /opt/libreoffice），创建软链：

```bash
ln -s /opt/libreoffice/program/soffice /usr/local/bin/soffice
```

## 五、重启后端生效

```bash
systemctl restart changjian-zhida
```

之后上传 doc/wps 文件，后端会自动优先用 LibreOffice 转换，解析精度大幅提升。

## 六、libstdc++ 依赖修复（重要）

如果运行 `soffice --headless --version` 报错：

```
/usr/lib64/libstdc++.so.6: version `GLIBCXX_3.4.29' not found
```

说明系统 libstdc++（GCC 10）太旧，LibreOffice 26.2 需要 GCC 11。用附带的两个 rpm 升级：

```bash
# 上传 libstdc++-11.2.1-9.4.el9.aarch64.rpm 和 libgcc-11.2.1-9.4.el9.aarch64.rpm 到服务器后：
rpm -Uvh --nodeps --force --oldpackage \
  libstdc++-11.2.1-9.4.el9.aarch64.rpm \
  libgcc-11.2.1-9.4.el9.aarch64.rpm
```

> 这两个包来自 Rocky Linux 9.0（GCC 11.2.1，glibc 2.34 与 openEuler 22.03 一致，向后兼容，覆盖系统旧 libstdc++ 是安全的）。`--oldpackage` 用于覆盖之前误装的 11.5.0 版本（该版本需要 glibc 2.35，不兼容）。

装完再验证：

```bash
soffice --headless --version
```

能打印版本号即成功，最后重启后端：

```bash
systemctl restart changjian-zhida
```

### 备选方案（rpm 装不上的话）

手动提取 .so 文件覆盖：

```bash
cd /tmp
rpm2cpio libstdc++-11.2.1-9.4.el9.aarch64.rpm | cpio -idmv
rpm2cpio libgcc-11.2.1-9.4.el9.aarch64.rpm | cpio -idmv
cp -f /tmp/usr/lib64/libstdc++.so.6* /usr/lib64/
cp -f /tmp/usr/lib64/libgcc_s.so.1* /usr/lib64/
ldconfig
```

