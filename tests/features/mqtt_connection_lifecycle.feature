# -*- coding: utf-8 -*-
Feature: MQTT 연결 및 구독 생명주기 (mqtt.py)
  push 알림이 안 들어오면 REST 폴백(1시간 간격)에만 의존하게 되는데,
  에러 로그 말고는 사용자가 알 방법이 없다. _count_subscribe_failures
  라는 순수 함수만 따로 검증했었고, 정작 이 함수들 자체는 한 번도
  호출해본 적이 없었다.

  Scenario: MQTT 연결이 정상적으로 성공한다
    Given 기기 목록 없이 MQTT 매니저가 있다
    When MQTT 연결을 시도해서 성공한다
    Then MQTT 연결 결과는 True 이어야 한다

  Scenario: ThinQMQTTClient 생성이 None을 반환하면 연결 실패로 처리된다
    Given 기기 목록 없이 MQTT 매니저가 있다
    When MQTT 연결 시도가 클라이언트 없이 끝난다
    Then MQTT 연결 결과는 False 이어야 한다

  Scenario: MQTT 연결 중 예외가 나도 크래시 없이 실패로 처리된다
    Given 기기 목록 없이 MQTT 매니저가 있다
    When MQTT 연결 시도 중 예외가 발생한다
    Then 예외가 발생하지 않아야 한다
    And MQTT 연결 결과는 False 이어야 한다

  Scenario: 클라이언트가 연결된 상태에서 구독을 시작하면 기기별로 push/event 구독하고 최종 연결한다
    Given 기기 2대와 연결된 클라이언트를 가진 MQTT 매니저가 있다
    When 구독을 시작한다
    Then thinq_api의 async_post_push_subscribe는 2 번 호출되어야 한다
    And thinq_api의 async_post_event_subscribe는 2 번 호출되어야 한다
    And MQTT 클라이언트의 async_connect_mqtt가 호출되어야 한다

  Scenario: 클라이언트가 없는 상태에서 구독을 시작하면 조용히 아무 것도 하지 않는다
    Given 기기 2대를 가졌지만 클라이언트가 연결되지 않은 MQTT 매니저가 있다
    When 구독을 시작한다
    Then 예외가 발생하지 않아야 한다
    And thinq_api의 async_post_push_subscribe는 0 번 호출되어야 한다

  Scenario: 구독을 해제하면 기기별로 push/event 구독 해제가 호출된다
    Given 기기 2대와 연결된 클라이언트를 가진 MQTT 매니저가 있다
    When 구독을 해제한다
    Then thinq_api의 async_delete_push_subscribe는 2 번 호출되어야 한다
    And thinq_api의 async_delete_event_subscribe는 2 번 호출되어야 한다

  Scenario: 등록된 기기가 없으면 구독 해제 시 아무 호출도 하지 않는다
    Given 기기 목록 없이 연결된 클라이언트를 가진 MQTT 매니저가 있다
    When 구독을 해제한다
    Then thinq_api의 async_delete_push_subscribe는 0 번 호출되어야 한다

  Scenario: 연결을 끊으면 구독 해제 후 클라이언트 연결도 끊긴다
    Given 기기 2대와 연결된 클라이언트를 가진 MQTT 매니저가 있다
    When MQTT 연결을 끊는다
    Then thinq_api의 async_delete_push_subscribe는 2 번 호출되어야 한다
    And MQTT 클라이언트의 async_disconnect가 호출되어야 한다

  Scenario: 클라이언트 연결 해제 자체가 실패해도 예외 없이 처리된다
    Given 기기 2대와 연결된 클라이언트를 가진 MQTT 매니저가 있다
    When 클라이언트 연결 해제가 실패하는 상태에서 MQTT 연결을 끊는다
    Then 예외가 발생하지 않아야 한다

  Scenario: 구독 갱신은 기기별로 event 구독만 다시 요청한다
    Given 기기 2대와 연결된 클라이언트를 가진 MQTT 매니저가 있다
    When 구독을 갱신한다
    Then thinq_api의 async_post_event_subscribe는 2 번 호출되어야 한다
    And thinq_api의 async_post_push_subscribe는 0 번 호출되어야 한다

  Scenario: 등록된 기기가 없으면 구독 갱신 시 아무 호출도 하지 않는다
    Given 기기 목록 없이 연결된 클라이언트를 가진 MQTT 매니저가 있다
    When 구독을 갱신한다
    Then thinq_api의 async_post_event_subscribe는 0 번 호출되어야 한다
