#!/usr/bin/env python3
"""
プロトコルバッファファイルからPythonコードを生成するスクリプト
"""

import os
import subprocess
import sys

def generate_proto_files():
    """プロトコルバッファファイルからPythonコードを生成"""
    
    # プロトコルバッファファイルのパス
    proto_dir = "external/vehicle-protocol/proto"
    signal_proto = os.path.join(proto_dir, "vehicle-shadow/signal.proto")
    types_proto = os.path.join(proto_dir, "vehicle-shadow/types.proto")
    
    # 出力ディレクトリ
    output_dir = "generated"
    
    # 出力ディレクトリを作成
    os.makedirs(output_dir, exist_ok=True)
    
    # protocコマンドを実行
    cmd = [
        "python", "-m", "grpc_tools.protoc",
        f"--proto_path={proto_dir}",
        f"--python_out={output_dir}",
        f"--grpc_python_out={output_dir}",
        signal_proto,
        types_proto
    ]
    
    try:
        print("プロトコルバッファファイルからPythonコードを生成中...")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("生成完了!")
        print(f"生成されたファイルは {output_dir} ディレクトリに保存されました")
        
        # 生成されたファイルの一覧を表示
        generated_files = os.listdir(output_dir)
        for file in generated_files:
            if file.endswith('.py'):
                print(f"  - {file}")
                
    except subprocess.CalledProcessError as e:
        print(f"エラー: {e}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        sys.exit(1)
    except FileNotFoundError:
        print("エラー: grpcio-toolsがインストールされていません")
        print("以下のコマンドでインストールしてください:")
        print("pip install grpcio-tools")
        sys.exit(1)

if __name__ == "__main__":
    generate_proto_files() 