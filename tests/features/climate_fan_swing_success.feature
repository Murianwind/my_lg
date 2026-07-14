# -*- coding: utf-8 -*-
Feature: 풍속·스윙 모드의 정상 성공 경로
  지금까지 async_set_fan_mode/async_set_swing_mode는 "재인증 필요라서
  스킵되는 경우"만 테스트되어 있었다. 정작 매일 실행되는, 정상적으로
  성공하는 경로는 한 번도 검증되지 않았었다.

  Scenario: 풍속을 정상적으로 설정하면 화면에 그대로 반영된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And wideq 팬/스윙 연동 기기(풍속 2단계, 수직 스텝 2단계)가 있다
    And 이 코디네이터와 wideq 기기로 climate 엔티티를 만든다
    When 풍속을 "SPEED_1"로 정상 설정한다
    Then 표시되는 풍속은 "SPEED_1" 이어야 한다

  Scenario: 수직 스텝이 있는 기기는 스윙을 설정하면 화면에 그대로 반영된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And wideq 팬/스윙 연동 기기(풍속 2단계, 수직 스텝 2단계)가 있다
    And 이 코디네이터와 wideq 기기로 climate 엔티티를 만든다
    When 스윙을 "STEP_1"로 정상 설정한다
    Then 표시되는 스윙 모드는 "STEP_1" 이어야 한다

  Scenario: 수직 스텝이 없는 기기는 스윙 설정 시 수평 스텝 메서드가 호출된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And wideq 수평 스텝 전용 팬/스윙 연동 기기(풍속 2단계, 수평 스텝 2단계)가 있다
    And 이 코디네이터와 wideq 기기로 climate 엔티티를 만든다
    When 스윙을 "HSTEP_0"로 정상 설정한다
    Then 수평 스텝 메서드가 "HSTEP_0"로 호출되어야 한다

  Scenario: 세션 만료 후 재시도한 호출이 InvalidCredentialError로 실패하면 재인증 필요로 표시된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And wideq 팬/스윙 연동 기기(풍속 2단계, 수직 스텝 2단계)가 있다
    And 이 코디네이터와 wideq 기기로 climate 엔티티를 만든다
    When 세션 만료 후 재시도가 InvalidCredentialError로 실패한다
    Then 예외가 발생하지 않아야 한다
    And wideq 결과는 False 이어야 한다
    And runtime_data의 재인증 필요 상태는 True 이어야 한다
