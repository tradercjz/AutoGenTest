
# 项目作用
读取AllTask.csv里的任务，然后把prepareCode和runCode组成脚本，提交到dolphindb的server运行。以测试生成的脚本是否正确。

如果脚本正确，会在目录的output子目录下，生成对应的测试case。同时，对于成功运行的case,则生成测试case的csv文件，这里默认固定为./output_test.csv了

测试case的文件名是csv(excel)文件里的编号id

如果脚本不能运行，则记录，最后运行完成之后，统一打印出来，类似于
--- Details of Failed Tasks ---
  ID: 110, Reason: prepareCode和runCode无法运行
  ID: 105, Reason: prepareCode和runCode无法运行
  ID: 106, Reason: prepareCode和runCode无法运行
  ID: 109, Reason: prepareCode和runCode无法运行

说明这些ID的对应的脚本不对，需要人工查看处理

# 配置
1. 可以修改main.py中的person_to_filter_for的值，修改为自己的名字，这样可以从所有的任务重找到自己需要处理的任务
2. 修改.env中的DDB_开头的配置（DEEPSEEK_开头的暂时项目用不到），用来连接dolphindb server验证脚本

# 运行
pip install -r requirements.txt
python main.py

# TODO
对于脚本不正确的，可以尝试用大模型结合RAG根据问题来生成，不过目前RAG太耗TOKEN，还没有优化，暂时都是人工处理了