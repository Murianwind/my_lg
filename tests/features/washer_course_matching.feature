# -*- coding: utf-8 -*-
Feature: 세탁기 코스 센서의 wideq-PAT 매칭 (sensor.py의 _async_build_washer_course_sensor)
  두 API가 같은 세탁기를 서로 다르게 노출하기 때문에 타입+별칭으로
  매칭해야 하는데, 매칭이 잘못돼도(엉뚱한 기기와 엮이거나 매칭 실패를
  놓치는 경우) 예외가 나지 않는 "조용한 버그" 유형이다.

  Scenario: wideq 클라이언트가 없으면 코스 센서를 만들지 않는다
    Given wideq 클라이언트 자체가 없는 세탁기 코스 센서 설정이 있다
    When 코스 센서를 만든다
    Then 코스 센서는 None 이어야 한다

  Scenario: wideq 기기 목록을 아직 못 받았으면 코스 센서를 만들지 않는다
    Given wideq 기기 목록이 None인 세탁기 코스 센서 설정이 있다
    When 코스 센서를 만든다
    Then 코스 센서는 None 이어야 한다

  Scenario: wideq 기기 목록에 세탁기가 하나도 없으면 코스 센서를 만들지 않는다
    Given wideq 기기 목록에 에어컨만 있는 세탁기 코스 센서 설정이 있다
    When 코스 센서를 만든다
    Then 코스 센서는 None 이어야 한다

  Scenario: wideq 세탁기가 있지만 별칭이 다르면 매칭되지 않아 코스 센서를 만들지 않는다
    Given wideq 기기 목록에 별칭이 다른 세탁기가 있는 코스 센서 설정이 있다
    When 코스 센서를 만든다
    Then 코스 센서는 None 이어야 한다

  Scenario: wideq 세탁기와 별칭이 일치하면 코스 센서가 만들어지고 기기가 등록된다
    Given wideq 기기 목록에 별칭이 일치하는 세탁기가 있는 코스 센서 설정이 있다
    When 코스 센서를 만든다
    Then 코스 센서는 None이 아니어야 한다
    And 세탁기 wideq 기기가 등록되어야 한다

  Scenario: wideq 모델 정보 로드가 실패(False)하면 코스 센서를 만들지 않는다
    Given wideq 기기 목록에 별칭이 일치하는 세탁기가 있는 코스 센서 설정이 있다
    When 모델 정보 로드가 실패하는 상태로 코스 센서를 만든다
    Then 코스 센서는 None 이어야 한다

  Scenario: wideq 모델 정보 로드 중 예외가 나도 크래시 없이 코스 센서를 만들지 않는다
    Given wideq 기기 목록에 별칭이 일치하는 세탁기가 있는 코스 센서 설정이 있다
    When 모델 정보 로드 중 예외가 발생하는 상태로 코스 센서를 만든다
    Then 코스 센서는 None 이어야 한다
