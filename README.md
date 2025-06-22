# Vehicle Shadow SignalService

このプロジェクトは、車両シャドウシステムのためのgRPCベースのSignalServiceを実装しています。CARLAシミュレーターとの連携を想定した設計になっています。

## 概要

SignalServiceは以下の機能を提供します：

- **Get**: 複数の信号値を取得
- **Set**: 複数の信号値を設定
- **Subscribe**: 信号の変更をリアルタイムでサブスクライブ
- **Unsubscribe**: サブスクリプションを解除
- **Lock**: 信号をロックして他のクライアントからの変更を防止
- **Unlock**: 信号のロックを解除

## セットアップ

### 1. 依存関係のインストール

```bash
pip install -r requirements.txt
```

### 2. プロトコルバッファファイルの生成

```bash
python generate_proto.py
```

これにより、`generated/`ディレクトリに以下のファイルが生成されます：
- `vehicle_shadow/signal_pb2.py`
- `vehicle_shadow/signal_pb2_grpc.py`
- `vehicle_shadow/types_pb2.py`

## 使用方法

### サーバーの起動

```bash
python signal_service.py
```

サーバーは`localhost:50051`で起動します。

### クライアントのテスト

別のターミナルで以下を実行：

```bash
python test_client.py
```

## ファイル構成

```
vehicle-carla/
├── external/vehicle-protocol/proto/vehicle-shadow/
│   ├── signal.proto          # SignalServiceの定義
│   └── types.proto           # データ型の定義
├── generated/                 # 生成されたPythonファイル
│   └── vehicle_shadow/
│       ├── signal_pb2.py
│       ├── signal_pb2_grpc.py
│       └── types_pb2.py
├── carla_client.py           # CARLA連携クライアントとSignalStore
├── signal_service.py         # gRPCサーバー実装
├── test_client.py            # テスト用クライアント
├── generate_proto.py         # プロトコルバッファ生成スクリプト
├── requirements.txt          # 依存関係
└── README.md                 # このファイル
```

## 実装の詳細

### SignalStore (carla_client.py)

信号データを管理するストアクラスです：

- 信号の保存と取得
- ロック機能
- サブスクライバー管理

### CarlaClient (carla_client.py)

CARLAシミュレーターとの連携クライアントです：

- CARLA関連の信号の初期化
- 車両データの更新メソッド
- 信号値の取得メソッド

### SignalServiceServicer (signal_service.py)

gRPCサービスの実装クラスです：

- 各RPCメソッドの実装
- SignalStoreとCarlaClientの統合
- エラーハンドリングとログ出力

### サンプルデータ

サーバー起動時に以下のCARLA信号が初期化されます：

#### 車両基本情報
- `Vehicle.Speed` (float, km/h)
- `Vehicle.Engine.RPM` (uint32, RPM)
- `Vehicle.Battery.Voltage` (float, V)
- `Vehicle.Temperature.Engine` (float, °C)

#### 車両位置・向き
- `Vehicle.Position.X` (float, m)
- `Vehicle.Position.Y` (float, m)
- `Vehicle.Position.Z` (float, m)
- `Vehicle.Orientation.Yaw` (float, degrees)

#### 車両制御
- `Vehicle.Doors.FrontLeft` (bool)
- `Vehicle.Lights.Headlights` (bool)

## API リファレンス

### Get

複数の信号を取得します。

```python
request = signal_pb2.GetRequest()
request.paths.extend(["Vehicle.Speed", "Vehicle.Engine.RPM"])
response = await stub.Get(request)
```

### Set

複数の信号値を設定します。

```python
request = signal_pb2.SetRequest()
request.token = "lock_token"  # ロックされた信号の場合

signal_request = signal_pb2.SetSignalRequest()
signal_request.path = "Vehicle.Speed"
signal_request.state.CopyFrom(state_object)
request.signals.append(signal_request)

response = await stub.Set(request)
```

### Subscribe

信号の変更をリアルタイムでサブスクライブします。

```python
request = signal_pb2.SubscribeRequest()
request.paths.extend(["Vehicle.Speed"])

async for response in stub.Subscribe(request):
    if response.signal:
        print(f"Signal changed: {response.signal.path}")
```

### Lock/Unlock

信号をロック/アンロックします。

```python
# ロック
lock_request = signal_pb2.LockRequest()
lock_request.paths.extend(["Vehicle.Speed"])
lock_response = await stub.Lock(lock_request)

# アンロック
unlock_request = signal_pb2.UnlockRequest()
unlock_request.token = lock_response.token
unlock_response = await stub.Unlock(unlock_request)
```

## CARLA連携機能

### CarlaClientの使用例

```python
from carla_client import SignalStore, CarlaClient

# SignalStoreとCarlaClientを初期化
signal_store = SignalStore()
carla_client = CarlaClient(signal_store)

# 車両データを更新
await carla_client.update_vehicle_speed(60.0)
await carla_client.update_engine_rpm(2500)
await carla_client.update_vehicle_position(100.0, 200.0, 0.5)
await carla_client.update_vehicle_orientation(45.0)

# 車両制御
await carla_client.toggle_headlights(True)
await carla_client.toggle_door("Vehicle.Doors.FrontLeft", True)

# 信号値を取得
speed = carla_client.get_signal_value("Vehicle.Speed")
position_x = carla_client.get_signal_value("Vehicle.Position.X")
```

## エラーハンドリング

各RPCメソッドは以下のエラーを適切に処理します：

- 信号が見つからない場合
- ロックされた信号への不正アクセス
- ネットワークエラー
- 無効なデータ型

## ログ

サーバーは以下のログレベルで動作します：

- INFO: 通常の操作ログ
- WARNING: 警告（信号が見つからない、ロック失敗など）
- ERROR: エラー（例外発生など）

## 注意事項

1. **プロトコルバッファファイルの生成**: 初回実行時は必ず`python generate_proto.py`を実行してください。

2. **ロック機能**: ロックされた信号は、ロックを取得したクライアントのみが変更できます。

3. **サブスクリプション**: サブスクリプションは非同期ストリームで実装されており、複数の信号変更をリアルタイムで受信できます。

4. **データ型**: 信号の値は`types.proto`で定義された型に従って設定する必要があります。

5. **CARLA連携**: CarlaClientはCARLAシミュレーターとの連携を想定した設計ですが、実際のCARLA APIとの連携は別途実装が必要です。

## トラブルシューティング

### プロトコルバッファファイルが見つからない

```bash
python generate_proto.py
```

### サーバーが起動しない

依存関係が正しくインストールされているか確認：

```bash
pip install -r requirements.txt
```

### クライアントがサーバーに接続できない

サーバーが起動しているか、ポート50051が利用可能か確認してください。

### 仮想環境の使用

システムが外部管理環境の場合は、仮想環境を使用してください：

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
``` 