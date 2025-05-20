from csv_parser import stream_filtered_records
from ddb import DatabaseSession

from concurrent.futures import ProcessPoolExecutor, as_completed
from dotenv import load_dotenv
import os
import time
import numpy as np
import pandas as pd

from llm_prompt import llm 

load_dotenv()

config = {
    'host': os.getenv("DDB_HOST"),
    'port': os.getenv("DDB_PORT"),
    'user': os.getenv("DDB_USER"),
    'passwd': os.getenv("DDB_PASSWD"),
}

#看去不需要大模型来写，固定规则生成就好
@llm.prompt()
def gen_test_via_llm(runCode: str, result: str) -> str:
    """
        我运行一个dolphindb脚本，得到了一个结果，结果如下: 
        {{ result }}

        现在，你需要根据这个结果，帮我编写一个校验脚本，就是验证result的变量，是上面的结果。
        这个结果，是通过
        {{ runCode }}
        来得到的。生成的校验脚本里，第一个是需要修改这个 运行的代码，把result改为result1，这样跟实际生成得到的reusult变量名区分开。
        之后，就是去验证这个result和result1是相等的。

        校验脚本例子，我们需要通过assert 语句+ ==这种或者eqObj函数判断，校验脚本里面的生成的变量需要和正确答案里面的不重名：

        比如：
        result1 = round(mean(daily_returns), 2)
        assert result1.values() == result.values()
        //或者
        assert eqObj(result1.values(),result.values()

        如果result1的类型是array，则通过assert eqObj(result1, result)来判断
        如果result的类型是table，则assert eqObj(result1.values(),result.values()
    """

# 根据result类型构建测试脚本
def gen_test(prepareCode, runCode, result) -> str:
    runCode = runCode.replace("result","result1")
    prepareCode = prepareCode.replace("result", "result1")
    testScript = f"""{prepareCode}\n{runCode}\n"""

    if isinstance(result, np.ndarray): 
        testScript += """assert(eqObj(result, result1))"""
    elif isinstance(result, list):  
        testScript += """assert(each(eqObj, result, result1))"""
    elif isinstance(result, float) or isinstance(result, int):
        testScript += """assert(result == result1)"""
    elif isinstance(result, pd.DataFrame): 
        testScript += """assert(each(eqObj, result1.values(), result.values()))"""
    else:
        raise Exception("result type not regonized:", type(result))

    return testScript

def save_script(id,script):
    # 默认输出到output下，生成的是测试脚本
    if not os.path.exists("./output"):
        os.makedirs("./output")
    with open(f"./output/{id}", "w+") as f:
        f.write(script)

def process_single_record(record_data):

    record_id = record_data['id']
    status = "success"
    print(f"[Process {os.getpid()}] Starting to process Record ID: {record_id}")
    result_message=""
    with DatabaseSession(config["host"], config["port"],  config["user"], config["passwd"]) as db:
        prepareCode = record_data["prepareCode"].strip().strip('"\'')
        runCode = record_data["runCode"].strip().strip('"\'')

        runScript = f"""
            {prepareCode}
            {runCode}
            result
        """
       
        try:
            script_ok, rsp = db.execute(runScript)
            if not script_ok:
                status = "failure"
                result_message = f"prepareCode和runCode无法运行"
            else:
                # 脚本运行OK，则开始生成自动脚本
                testScript = gen_test(prepareCode, runCode, rsp)
                save_script(record_id,testScript)
                result_message = f"Successfully processed Record ID: {record_id} (simulated by process {os.getpid()})."
        except Exception as e:
            status = "failure"
            result_message = str(e)
    print(f"[Process {os.getpid()}] Finished processing Record ID: {record_id}")
   
    return {"status": status, "id": record_id, "message": result_message}


if __name__ == "__main__":

    #所有的任务
    dummy_filepath = "AllTask.csv"
    #筛选出需要你处理的
    person_to_filter_for = "津枝"
    max_workers=10
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor: 

        future_to_record_id  = {}
        results_summary = []
        processed_count = 0

        for record in stream_filtered_records(dummy_filepath, person_to_filter_for):
            future = executor.submit(process_single_record, record)
            future_to_record_id[future] = record['id']
        print(f"Submitted {len(future_to_record_id)} tasks to the process pool.")

        successful_tasks = []
        failed_tasks = [] 
        for future in as_completed(future_to_record_id):
            record_id_completed = future_to_record_id[future]
            try:
                result  = future.result()
                if result["status"] == "success":
                    successful_tasks.append(result)
                else:
                    failed_tasks.append(result)
                processed_count += 1
            except Exception as exc:
                error_message = f"Record ID {record_id_completed} generated an exception: {exc}"
                print(error_message)

    print("\n--- Parallel Processing Summary ---")
    print(f"Total records processed (or attempted): {processed_count} out of {len(future_to_record_id)} submitted.")

    #打印失败的编号，需要人工处理，先把脚本修改正确，再去生成测试代码
    if failed_tasks:
        print("\n--- Details of Failed Tasks ---")
        for failure in failed_tasks:
            print(f"  ID: {failure['id']}, Reason: {failure['message']}")
    else:
        print("All tasks processed successfully (or no tasks to process).")
