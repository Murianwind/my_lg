# -*- coding: utf-8 -*-
Feature: MQTT 메시지 처리의 견고성
  MQTT 콜백은 awscrt C 확장 라이브러리의 콜백 디스패치 안에서 직접
  호출되기 때문에, 여기서 예외가 새어나가면 이후 이 스레드의 동작을
  신뢰할 수 없게 된다. 깨진 페이로드나 알 수 없는 기기의 메시지가
  와도 예외 없이 조용히 처리되어야 한다.

  Scenario: 깨진 UTF-8 페이로드는 예외 없이 무시된다
    When 깨진 UTF-8 바이트 페이로드로 MQTT 메시지를 수신한다
    Then MQTT 처리는 예외를 던지지 않아야 한다

  Scenario: 잘못된 JSON 페이로드는 예외 없이 무시된다
    When 잘못된 JSON 페이로드로 MQTT 메시지를 수신한다
    Then MQTT 처리는 예외를 던지지 않아야 한다

  Scenario: 정상적인 DEVICE_STATUS 메시지는 해당 코디네이터로 전달된다
    When 알려진 기기의 정상적인 DEVICE_STATUS 메시지를 수신한다
    Then 해당 코디네이터의 handle_mqtt_status가 호출되어야 한다
