# -*- coding: utf-8 -*-
Feature: MQTT 구독 실패 집계 (mqtt.py의 _count_subscribe_failures)
  순수 함수라 hass나 코디네이터 없이도 바로 검증 가능하다. 여기가
  잘못되면 진짜 구독 실패를 조용히 숨기거나, 반대로 정상인데 계속
  에러 로그를 찍을 수 있다.

  Scenario: 빈 결과 목록은 실패 0건이다
    When 빈 결과 목록으로 구독 실패 개수를 센다
    Then 구독 실패 개수는 0 이어야 한다

  Scenario: 이미 구독됨(ALREADY_SUBSCRIBED_PUSH) 에러는 실패로 세지 않는다
    When 이미_구독됨_에러만 있는 결과 목록으로 구독 실패 개수를 센다
    Then 구독 실패 개수는 0 이어야 한다

  Scenario: 다른 종류의 ThinQ API 에러는 실패로 센다
    When 다른_thinq_에러가_섞인 결과 목록으로 구독 실패 개수를 센다
    Then 구독 실패 개수는 1 이어야 한다

  Scenario: TypeError나 ValueError도 실패로 센다
    When typeerror가_섞인 결과 목록으로 구독 실패 개수를 센다
    Then 구독 실패 개수는 1 이어야 한다
