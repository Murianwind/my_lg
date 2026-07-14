# -*- coding: utf-8 -*-
Feature: wideq 명령 재시도 엔진의 나머지 실패 분기 (climate.py의 _async_send_wideq_command)
  팬속도/스윙/온도가 전부 거치는 재시도·에러 처리 로직이다. 이번 세션
  중 이미 실제 버그가 두 번 발견된 곳이라, 나머지 분기도 확인해둘
  가치가 크다.

  Scenario: 기기가 오프라인(NotConnectedError)이면 예외 없이 실패로 처리된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And wideq 팬/스윙 연동 기기(풍속 2단계, 수직 스텝 2단계)가 있다
    And 이 코디네이터와 wideq 기기로 climate 엔티티를 만든다
    When wideq 명령이 NotConnectedError로 실패한다
    Then 예외가 발생하지 않아야 한다
    And wideq 결과는 False 이어야 한다

  Scenario: 세션이 만료됐다가 재인증 후 재시도가 성공하면 정상 처리된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And wideq 팬/스윙 연동 기기(풍속 2단계, 수직 스텝 2단계)가 있다
    And 이 코디네이터와 wideq 기기로 climate 엔티티를 만든다
    When wideq 세션이 만료됐다가 재시도가 성공한다
    Then 예외가 발생하지 않아야 한다
    And wideq 결과는 True 이어야 한다

  Scenario: 세션 갱신 자체가 실패하면 ServiceValidationError가 발생한다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And wideq 팬/스윙 연동 기기(풍속 2단계, 수직 스텝 2단계)가 있다
    And 이 코디네이터와 wideq 기기로 climate 엔티티를 만든다
    When wideq 세션 갱신 자체가 실패한다
    Then 예외는 ServiceValidationError 이어야 한다

  Scenario: 일시적 에러 코드로 실패했다가 재시도에서 성공하면 정상 처리된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And wideq 팬/스윙 연동 기기(풍속 2단계, 수직 스텝 2단계)가 있다
    And 이 코디네이터와 wideq 기기로 climate 엔티티를 만든다
    When wideq가 일시적 에러 코드로 실패했다가 재시도에서 성공한다
    Then 예외가 발생하지 않아야 한다
    And wideq 결과는 True 이어야 한다

  Scenario: 일시적 에러 코드가 재시도에서도 계속되면 ServiceValidationError가 발생한다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And wideq 팬/스윙 연동 기기(풍속 2단계, 수직 스텝 2단계)가 있다
    And 이 코디네이터와 wideq 기기로 climate 엔티티를 만든다
    When wideq가 일시적 에러 코드로 계속 실패한다
    Then 예외는 ServiceValidationError 이어야 한다

  Scenario: 일시적이지 않은 에러 코드는 재시도 없이 즉시 실패한다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And wideq 팬/스윙 연동 기기(풍속 2단계, 수직 스텝 2단계)가 있다
    And 이 코디네이터와 wideq 기기로 climate 엔티티를 만든다
    When wideq가 일시적이지 않은 에러 코드로 실패한다
    Then 예외는 ServiceValidationError 이어야 한다
    And wideq 호출 횟수는 1 이어야 한다
