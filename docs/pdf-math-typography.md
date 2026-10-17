# 数学练习卷符号与打印排版

专项练习卷使用随项目提供的 STIX Two Math 字体排版公式。PDF 会嵌入实际用到的字形，因此学生在电脑或打印机上打开文件时不需要安装数学字体。中文正文继续使用系统中文字体。

公式输入支持常见 LaTeX 写法，也会识别生成内容中的 `pi`、`sqrt(3)`、`<=`、`!=`、`*` 和上下标。图示符号表中的集合关系、逻辑量词、常用数集、区间、绝对值、函数与数列、对数、导数、极限、积分、判别式、角、弧、向量、点积和叉积均有对应字形。

推荐写法示例：

```text
\mathbb{R}, \mathbb{N}_{+}, A\subseteq B, A\nsubseteq B
f^{-1}(x), a_n, \log_a x, \int_a^b f(x)\,dx
\widehat{AB}, \vec{a}, \|\vec{a}\|, \vec{a}\cdot\vec{b}
```

分数使用清晰的分数斜线，平方根使用根号，上下标采用真实基线排版。间隔和关系符号会按数学读法留白。每道题后提供 38 mm 的作答区，并绘制五条书写线。页面使用 A4 纵向尺寸，学生可以按实际大小打印。

字体及许可证来自 [STIX 字体项目](https://github.com/stipub/stixfonts)，项目按 SIL Open Font License 1.1 发布。许可证文本保存在 `backend/app/assets/fonts/OFL.txt`。
