# -*- coding: utf-8 -*-
Feature: 에어컨 climate 엔티티의 wideq 유무에 따른 동작
  풍속/회전 제어는 wideq 없이는 아예 제공될 수 없고, 목표 온도는
  wideq가 있으면 0.5도 단위, 없으면 PAT로 1도 단위 폴백해야 한다.
  wideq가 아예 끊긴 상황에서도 최소한 온도 조절은 계속 가능해야 한다.

  Scenario: wideq 연동 기기가 있으면 0.5도 단위와 팬/스윙 기능이 제공된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And wideq 팬/스윙 연동 기기(풍속 2단계, 수직 스텝 2단계)가 있다
    When 이 코디네이터와 wideq 기기로 climate 엔티티를 만든다
    Then 목표 온도 스텝은 0.5 이어야 한다
    And climate 엔티티는 팬 모드 기능을 지원해야 한다
    And climate 엔티티는 스윙 모드 기능을 지원해야 한다

  Scenario: wideq 연동이 없으면 1도 단위로 폴백하고 팬/스윙은 지원되지 않는다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    When wideq 기기 없이 climate 엔티티를 만든다
    Then 목표 온도 스텝은 1.0 이어야 한다
    And climate 엔티티는 팬 모드 기능을 지원하지 않아야 한다
    And climate 엔티티는 스윙 모드 기능을 지원하지 않아야 한다

  Scenario: wideq가 없을 때 온도를 설정하면 PAT로 반올림되어 전달된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And wideq 기기 없이 climate 엔티티를 만든다
    When 목표 온도를 24.5도로 설정한다
    Then PAT의 냉방 목표 온도 설정 메서드가 반올림된 값으로 호출되어야 한다

  Scenario: 디바운스 대기 중 엔티티가 제거되면 대기 중인 온도 전송 작업이 취소된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And wideq 팬/스윙 연동 기기(풍속 2단계, 수직 스텝 2단계)가 있다
    And 이 코디네이터와 wideq 기기로 climate 엔티티를 만든다
    When 목표 온도를 24.5도로 설정한 직후 엔티티가 제거된다
    Then 대기 중인 온도 전송 작업은 취소되어야 한다
